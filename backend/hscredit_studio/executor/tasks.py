"""Celery 任务 — 节点执行入口.

依据 :file:`docs/design/01-system-architecture.md` 第 1.5 节,
单个节点执行流程:

1. 加载 :class:`NodeExecution` 记录与 Run,设置租户上下文。
2. 标记 ``running``。
3. 从 :class:`NodeRegistry` 拿到节点类。
4. 加载上游节点的产物(从 MinIO / artifact_paths)。
5. 缓存检查(Redis):按 ``input_hash`` 命中则拷贝产物路径,直接 ``success``。
6. 缓存未命中:执行 :meth:`BaseNode.run` → 落盘(MinIO)→ 写缓存 → ``success``。
7. 异常路径:业务错误不重试,系统错误按 ``contract.retryable`` 重试。

异步包装: Celery worker 进程是同步上下文,直接 ``await`` 会报错。
本模块用 ``asyncio.run(_run_node_async(...))`` 把异步逻辑包到事件循环里。
worker 启动后,所有 ``run_node.apply_async`` 调用走的是同一进程内的
事件循环,效率与单次 ``run`` 一致。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import pickle
import traceback
from datetime import datetime
from typing import Any
from uuid import UUID

from hscredit_studio.celery_app import celery_app
from hscredit_studio.core.config import settings
from hscredit_studio.core.database import session_scope, set_tenant_context
from hscredit_studio.core.exceptions import HSCreditWorkflowError
from hscredit_studio.core.logging import get_logger
from hscredit_studio.executor.coordinator import RunCoordinator
from hscredit_studio.models import NodeExecution, Run
from hscredit_studio.nodes.registry import NodeRegistry
from hscredit_studio.services.artifacts import (
    infer_artifact_type,
    load_node_inputs,
    save_node_output,
)
from hscredit_studio.services.cache import CacheKeyGenerator, close_cache_client, get_cache_client
from hscredit_studio.services.events import publish_event

_log = get_logger(__name__)


def _compute_input_hash(params: dict[str, Any], input_metadata: dict[str, Any]) -> str:
    """计算输入哈希(用于缓存键).

    Args:
        params: 节点参数快照。
        input_metadata: 输入数据的元描述(类型 / 名称 / hash 等),
                       不要包含完整 DataFrame 内容,只描述它。

    Returns:
        64 字符的 sha256 hex。
    """
    payload = json.dumps(
        {"params": params, "inputs": input_metadata},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@celery_app.task(
    name="hscredit_studio.executor.tasks.run_node",
    bind=True,
    acks_late=True,
    soft_time_limit=300,
    time_limit=360,
    max_retries=0,  # 由 RunCoordinator 控制重试
)
def run_node(self, node_exec_id: str) -> dict[str, Any]:
    """执行单个节点 — Celery 任务入口(通用队列 ``nodes-general``).

    Args:
        node_exec_id: :class:`NodeExecution` UUID 字符串形式。

    Returns:
        执行结果描述 dict, 包含 ``status`` 字段
        (``success`` / ``cached`` / ``failed`` / ``missing`` / ``no_run`` /
        ``node_not_found``)。
    """
    try:
        return asyncio.run(_run_node_async(UUID(node_exec_id)))
    finally:
        # 关闭 redis.asyncio 连接池，避免下次 asyncio.run() 持有的旧 event loop
        # 引发 RuntimeError（celery solo worker 下每次任务都是新 event loop）
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(close_cache_client())
            loop.close()
        except Exception as e:
            # 关闭失败不影响任务主流程（连接池随进程退出释放）
            _log.debug("cache_close_skipped", error=str(e))


async def _run_node_async(node_exec_id: UUID) -> dict[str, Any]:
    """节点执行的异步主流程.

    与 :func:`run_node` 配对;此函数不直接暴露给 Celery。

    末尾关闭 Redis 连接池：celery solo worker 下 ``asyncio.run()`` 每次创建
    新事件循环，跨任务复用的 redis.asyncio client 会持有已关闭 loop 引发
    RuntimeError。
    """
    async with session_scope() as session:
        ne = await session.get(NodeExecution, node_exec_id)
        if ne is None:
            _log.error("node_exec_not_found", node_exec_id=str(node_exec_id))
            return {"status": "missing"}

        run = await session.get(Run, ne.run_id)
        if run is None:
            return {"status": "no_run"}

        if run.tenant_id:
            await set_tenant_context(session, str(run.tenant_id))

        # 标记 running(独立 commit,即便后续失败也能在 DB 看到)
        ne.status = "running"
        ne.started_at = datetime.utcnow()
        await session.commit()
        # 推送 running 状态
        await publish_event(
            ne.run_id,
            "node_execution",
            node_id=ne.node_id,
            node_type=ne.node_type,
            status=ne.status,
        )
        await publish_event(
            ne.run_id,
            "log",
            node_id=ne.node_id,
            stream="system",
            level="info",
            message=f"开始执行 {ne.node_type}",
        )

        node_cls = NodeRegistry.try_get(ne.node_type)
        if node_cls is None:
            await RunCoordinator.handle_node_failure(
                node_exec_id,
                {
                    "code": "E_NODE_NOT_FOUND",
                    "message": f"节点类型 {ne.node_type} 未注册",
                    "non_retryable": True,
                },
                retry=False,
            )
            return {"status": "node_not_found"}

        node_instance = node_cls()

        try:
            # 1. 加载输入(从上游节点的 artifact_paths)
            inputs = await _load_inputs(session, ne)
            input_meta = {k: str(type(v).__name__) for k, v in inputs.items()}

            # 2. 缓存检查
            params = ne.params or {}
            input_hash = _compute_input_hash(params, input_meta)
            cache = await get_cache_client()
            cache_key = CacheKeyGenerator.node_input_key(
                tenant_id=str(run.tenant_id) if run.tenant_id else "anonymous",
                node_type=ne.node_type,
                input_hash=input_hash,
            )
            cached_bytes = await cache.get(cache_key)
            if cached_bytes:
                # 缓存命中
                cached_data = pickle.loads(cached_bytes) if isinstance(cached_bytes, bytes) else cached_bytes
                ne.status = "cached_hit"
                ne.cached_from_run_id = UUID(cached_data["source_run_id"]) if cached_data.get("source_run_id") else None
                ne.finished_at = datetime.utcnow()
                await session.commit()
                await RunCoordinator.handle_node_success(
                    node_exec_id,
                    {
                        "output_hash": cached_data.get("output_hash"),
                        "artifact_paths": cached_data.get("artifact_paths") or {},
                    },
                )
                _log.info(
                    "node_cache_hit",
                    node_exec_id=str(node_exec_id),
                    source_run_id=str(ne.cached_from_run_id),
                )
                await publish_event(
                    ne.run_id,
                    "log",
                    node_id=ne.node_id,
                    stream="system",
                    level="info",
                    message=f"缓存命中（来源 run: {ne.cached_from_run_id}）",
                )
                return {"status": "cached"}

            # 3. 执行 (Phase 3 B14: 通过沙箱执行, 默认 subprocess 后端; B17: 采集资源用量)
            from hscredit_studio.services.sandbox import (
                SandboxError,
                SandboxOOMError,
                SandboxTimeoutError,
                get_sandbox_backend,
            )

            sandbox = get_sandbox_backend()
            node_instance.validate_inputs(inputs)
            node_instance.validate_params(params)
            outputs, resource_usage = await sandbox.execute_with_usage(
                ne.node_type, inputs, params
            )

            # Phase 3 B17: 落库资源用量 (失败仅 WARN, 不阻塞主流程)
            from hscredit_studio.services.resource_usage import record_resource_usage

            await record_resource_usage(
                node_exec_id=node_exec_id,
                node_type=ne.node_type,
                tenant_id=run.tenant_id,
                usage=resource_usage,
                sandbox_backend=settings.sandbox_backend,
            )

            # 4. 产物落盘（统一在 executor 层序列化 + 上传 + 写 NodeArtifact）
            artifact_paths, output_hash = await _save_outputs(
                session=session,
                tenant_id=run.tenant_id,
                ne=ne,
                outputs=outputs,
            )

            # 6. 写缓存
            cache_payload = pickle.dumps(
                {
                    "source_run_id": str(ne.run_id),
                    "output_hash": output_hash,
                    "artifact_paths": artifact_paths,
                }
            )
            ttl = node_cls.contract.cache.ttl_seconds or 86400
            await cache.set(cache_key, cache_payload, ex=ttl)

            # 7. 更新状态 + 推进下游
            await RunCoordinator.handle_node_success(
                node_exec_id,
                {
                    "output_hash": output_hash,
                    "artifact_paths": artifact_paths,
                },
            )

            _log.info(
                "node_success",
                node_exec_id=str(node_exec_id),
                node_type=ne.node_type,
                outputs_count=len(outputs),
            )
            await publish_event(
                ne.run_id,
                "log",
                node_id=ne.node_id,
                stream="system",
                level="info",
                message=f"{ne.node_type} 执行成功（{len(outputs)} 个输出）",
            )
            return {"status": "success", "outputs_count": len(outputs)}

        except HSCreditWorkflowError as e:
            # 业务错误(4xx / 业务校验失败)→ 不重试
            error_info = {"code": e.code, "message": str(e), "details": e.details}
            retryable = e.http_status < 500 and node_cls.contract.retryable
            await RunCoordinator.handle_node_failure(
                node_exec_id,
                error_info,
                retry=retryable,
            )
            _log.warning(
                "node_business_error",
                node_exec_id=str(node_exec_id),
                code=e.code,
                message=str(e),
                http_status=e.http_status,
            )
            await publish_event(
                ne.run_id,
                "log",
                node_id=ne.node_id,
                stream="stderr",
                level="error",
                message=f"{ne.node_type} 业务错误: {e.code} - {e}",
            )
            return {"status": "failed", "error": error_info}

        except SandboxTimeoutError as e:
            # Phase 3 B14: 沙箱超时, 标记特定 code 便于监控告警
            from hscredit_studio.core.config import settings as _sandbox_settings

            error_info = {
                "code": "SANDBOX_TIMEOUT",
                "message": str(e),
                "details": {
                    "node_type": ne.node_type,
                    "timeout_sec": _sandbox_settings.sandbox_timeout_sec,
                },
            }
            await RunCoordinator.handle_node_failure(
                node_exec_id,
                error_info,
                retry=node_cls.contract.retryable,
            )
            _log.warning(
                "sandbox_timeout",
                node_exec_id=str(node_exec_id),
                node_type=ne.node_type,
            )
            await publish_event(
                ne.run_id,
                "log",
                node_id=ne.node_id,
                stream="stderr",
                level="error",
                message=f"{ne.node_type} 沙箱执行超时: {e}",
            )
            return {"status": "failed", "error": error_info}

        except SandboxOOMError as e:
            from hscredit_studio.core.config import settings as _sandbox_settings

            error_info = {
                "code": "SANDBOX_OOM",
                "message": str(e),
                "details": {
                    "node_type": ne.node_type,
                    "memory_limit": _sandbox_settings.sandbox_memory_limit,
                },
            }
            await RunCoordinator.handle_node_failure(
                node_exec_id,
                error_info,
                retry=node_cls.contract.retryable,
            )
            _log.warning(
                "sandbox_oom",
                node_exec_id=str(node_exec_id),
                node_type=ne.node_type,
            )
            await publish_event(
                ne.run_id,
                "log",
                node_id=ne.node_id,
                stream="stderr",
                level="error",
                message=f"{ne.node_type} 沙箱 OOM: {e}",
            )
            return {"status": "failed", "error": error_info}

        except SandboxError as e:
            error_info = {
                "code": "E_SANDBOX_EXECUTION",
                "message": str(e),
                "traceback": traceback.format_exc()[:2000],
            }
            await RunCoordinator.handle_node_failure(
                node_exec_id,
                error_info,
                retry=node_cls.contract.retryable,
            )
            _log.error(
                "sandbox_execution_failed",
                node_exec_id=str(node_exec_id),
                node_type=ne.node_type,
                error=str(e),
            )
            await publish_event(
                ne.run_id,
                "log",
                node_id=ne.node_id,
                stream="stderr",
                level="error",
                message=f"{ne.node_type} 沙箱执行错误: {e}",
            )
            return {"status": "failed", "error": error_info}

        except Exception as e:
            # 系统错误 → 按 contract.retryable 决定是否重试
            error_info = {
                "code": "E_NODE_EXECUTION",
                "message": str(e),
                "traceback": traceback.format_exc()[:2000],
            }
            await RunCoordinator.handle_node_failure(
                node_exec_id,
                error_info,
                retry=node_cls.contract.retryable,
            )
            _log.exception(
                "node_unhandled_error",
                node_exec_id=str(node_exec_id),
                node_type=ne.node_type,
            )
            await publish_event(
                ne.run_id,
                "log",
                node_id=ne.node_id,
                stream="stderr",
                level="error",
                message=f"{ne.node_type} 系统异常: {type(e).__name__}: {e}",
            )
            return {"status": "failed", "error": error_info}


async def _load_inputs(
    session: Any,  # AsyncSession — 用 Any 避免引入 SQLAlchemy 类型依赖
    ne: NodeExecution,
) -> dict[str, Any]:
    """从上游节点的 ``artifact_paths`` 反序列化为 Python 对象.

    调用 :func:`hscredit_studio.services.artifacts.load_node_inputs`，
    该函数会从 S3 下载字节流并按 artifact_type 推断反序列化（DataFrame → parquet、
    Model → pickle、dict → JSON 等）。

    artifact_paths key 格式 ``{upstream_node_id}.{output_name}``（避免同名覆盖），
    此处拆出真正的 ``output_name`` 并把同名 value 合并为 list。

    返回的字典 ``inputs`` 直接传给 ``node_instance.run(inputs, params)``。
    """
    if ne.tenant_id is None:
        # 系统级无租户节点（罕见）；上游产物不在 S3，直接空入参
        return {}
    upstream_paths = ne.artifact_paths or {}
    if not upstream_paths:
        return {}
    return await load_node_inputs(
        session=session,
        tenant_id=ne.tenant_id,
        artifact_paths=upstream_paths,
        _input_ne=ne,
    )


async def _save_outputs(
    session: Any,
    tenant_id: UUID | None,
    ne: NodeExecution,
    outputs: dict[str, Any],
) -> tuple[dict[str, str], str]:
    """序列化 + 上传 + 写 NodeArtifact + 计算输出 hash.

    Returns
    -------
    (artifact_paths, output_hash)
        ``artifact_paths`` — ``{output_name: storage_key}``，写入
        ``NodeExecution.artifact_paths`` 与 Redis 缓存。
        ``output_hash`` — 拼接所有产物 sha256 的稳定字符串，用于跨 run 比对。

    空值（None / 空 bytes / 空字符串 / 空 DataFrame）直接跳过，不写入 S3 与
    ``node_artifacts`` 表，避免重复键冲突。
    """
    if not outputs:
        return {}, ""

    artifact_paths: dict[str, str] = {}
    sha_list: list[str] = []

    if tenant_id is None:
        # 系统级无租户：仅记录类型信息，不上传（实际生产不应出现）
        for key, value in outputs.items():
            atype = infer_artifact_type(value)
            artifact_paths[key] = f"<no-tenant>/runs/{ne.run_id}/nodes/{ne.node_exec_id}/{key}.{atype}"
            sha_list.append(f"{key}:{atype}:no-data")
        return artifact_paths, hashlib.sha256("|".join(sha_list).encode("utf-8")).hexdigest()

    for output_name, value in outputs.items():
        # 跳过空值，避免 S3 重复键 + DB 唯一冲突
        if value is None:
            continue
        if isinstance(value, (bytes, str)) and len(value) == 0:
            continue
        try:
            import pandas as _pd

            if isinstance(value, _pd.DataFrame) and value.empty:
                continue
        except ImportError:
            pass
        storage_key = await save_node_output(
            session=session,
            tenant_id=tenant_id,
            ne=ne,
            output_name=output_name,
            value=value,
        )
        artifact_paths[output_name] = storage_key
        atype = infer_artifact_type(value)
        sha_list.append(f"{output_name}:{atype}:{type(value).__name__}")

    output_hash = hashlib.sha256("|".join(sha_list).encode("utf-8")).hexdigest() if sha_list else ""
    return artifact_paths, output_hash


@celery_app.task(
    name="hscredit_studio.executor.tasks.run_heavy_node",
    bind=True,
    acks_late=True,
    soft_time_limit=3600,
    time_limit=3700,
    max_retries=0,
)
def run_heavy_node(self, node_exec_id: str) -> dict[str, Any]:
    """重节点执行入口(队列 ``nodes-heavy``).

    通过 Celery 路由(``celery_app.conf.task_routes``)把重节点转发到
    ``nodes-heavy`` 队列,该队列由独立的 Worker 进程消费,
    可限制 CPU / 内存配额。

    与 :func:`run_node` 共享同一异步主流程 — 区别仅在队列。
    """
    # 复用 _run_node_async;路由由 Celery task_routes 决定。
    return asyncio.run(_run_node_async(UUID(node_exec_id)))


__all__ = ["run_heavy_node", "run_node"]
