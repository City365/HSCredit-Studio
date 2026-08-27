"""Run 协调器 — 提交 Run 后管理节点执行的状态推进.

依据 :file:`docs/design/01-system-architecture.md` 第 1.5 节
以及 :file:`docs/design/06-non-functional.md` 第 6.1 节的状态机,
协调器负责:

- Run 提交后把入度为 0 的节点入 Celery 队列 (:meth:`RunCoordinator.enqueue_initial_nodes`)。
- 单个节点执行成功 / 失败后推进状态机,并把下游就绪节点入队
  (:meth:`RunCoordinator.handle_node_success` / :meth:`handle_node_failure`)。
- 终态判定:所有节点 ``success`` / ``skipped`` → Run ``success``;
           出现 ``failed`` (重试用尽) → Run ``failed``。

设计要点:

- 不直接调 Celery,而是通过 ``run_node.apply_async`` 发任务;由
  :mod:`tasks` 提供 ``run_node`` 的实现,这里用延迟 import 避免循环依赖。
- 所有数据库操作都走 :func:`session_scope`,自动 commit / rollback。
- 多租户:读 Run / NodeExecution 前调用 :func:`set_tenant_context`
  设置 RLS context。
- 重试策略:``retry_count < 3`` 且错误可重试 → 指数退避 ``countdown = 2 ** retry_count``。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.database import session_scope, set_tenant_context
from hscredit_studio.core.exceptions import FeatureNotFoundError, NodeExecutionError
from hscredit_studio.core.logging import get_logger
from hscredit_studio.models import (
    NodeExecution,
    Run,
    WorkflowVersion,
)
from hscredit_studio.schemas.workflow import WorkflowDefinition
from hscredit_studio.executor.parser import (
    get_initial_nodes,
    parse_workflow_definition,
)
from hscredit_studio.services.events import publish_event

_log = get_logger(__name__)

# 重试上限(超过则置 failed)
_MAX_RETRIES = 3


class RunCoordinator:
    """Run 协调器 — 协调 Run / NodeExecution / Celery 任务的状态推进.

    所有方法均为 ``staticmethod``;无状态;
    可在 Celery worker / API handler / scheduler 任一处调用。
    """

    @staticmethod
    async def enqueue_initial_nodes(run_id: UUID) -> int:
        """Run 提交后,把入度为 0 的节点入 Celery 队列.

        Args:
            run_id: Run UUID。

        Returns:
            入队的节点数量。

        Raises:
            FeatureNotFoundError: Run 不存在。
        """
        from hscredit_studio.executor.tasks import run_node  # 延迟导入避免循环

        async with session_scope() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise FeatureNotFoundError(
                    f"Run {run_id} 不存在",
                    details={"run_id": str(run_id)},
                )
            if run.tenant_id:
                await set_tenant_context(session, str(run.tenant_id))

            version = await session.get(WorkflowVersion, run.workflow_version_id)
            if version is None:
                raise FeatureNotFoundError(
                    f"WorkflowVersion {run.workflow_version_id} 不存在",
                    details={"workflow_version_id": str(run.workflow_version_id)},
                )
            definition = WorkflowDefinition(**version.definition)
            plans = parse_workflow_definition(definition)

            initial_ids = get_initial_nodes(plans)
            queued_count = 0
            for nid in initial_ids:
                ne = await _get_ne_by_node_id(session, run_id, nid)
                if ne is None:
                    _log.warning(
                        "node_execution_missing",
                        run_id=str(run_id),
                        node_id=nid,
                    )
                    continue
                # 入 Celery 通用队列
                run_node.apply_async(args=[str(ne.node_exec_id)], queue="nodes-general")
                queued_count += 1

            # 更新 run 状态
            run.status = "running"
            run.started_at = datetime.utcnow()
            await session.commit()

            _log.info(
                "run_started",
                run_id=str(run_id),
                initial_nodes=queued_count,
                total_nodes=len(plans),
            )
            # 推送 run_status 事件
            await publish_event(
                run_id, "run_status",
                status=run.status,
                total_nodes=len(plans),
                initial_nodes=queued_count,
            )
            return queued_count

    @staticmethod
    async def handle_node_success(
        node_exec_id: UUID,
        outputs_meta: dict[str, Any],
    ) -> None:
        """节点执行成功 — 更新状态、触发下游。

        Args:
            node_exec_id: NodeExecution UUID。
            outputs_meta: 产物元数据,至少包含 ``output_hash`` 和 ``artifact_paths``。
        """
        from hscredit_studio.executor.tasks import run_node  # 延迟导入

        async with session_scope() as session:
            ne = await session.get(NodeExecution, node_exec_id)
            if ne is None:
                _log.warning("node_exec_not_found", node_exec_id=str(node_exec_id))
                return

            ne.status = "success"
            ne.finished_at = datetime.utcnow()
            ne.output_hash = outputs_meta.get("output_hash")
            ne.artifact_paths = outputs_meta.get("artifact_paths") or {}

            run = await session.get(Run, ne.run_id)
            if run is None:
                _log.warning(
                    "run_missing_for_node",
                    node_exec_id=str(node_exec_id),
                    run_id=str(ne.run_id),
                )
                return

            # 解析 workflow 定义(用于查找下游节点)
            version = await session.get(WorkflowVersion, run.workflow_version_id)
            if version is None:
                _log.error(
                    "workflow_version_missing",
                    workflow_version_id=str(run.workflow_version_id),
                )
                return
            definition = WorkflowDefinition(**version.definition)
            plans = parse_workflow_definition(definition)
            plan = plans.get(ne.node_id)
            if plan is None:
                _log.error("plan_not_found", node_id=ne.node_id)
                return

            # 加载同 run 所有 NodeExecution,用于判定下游是否就绪
            all_ne = (
                await session.scalars(
                    select(NodeExecution).where(NodeExecution.run_id == ne.run_id)
                )
            ).all()
            status_by_id: dict[str, str] = {n.node_id: n.status for n in all_ne}

            # 把当前节点加入 completed 集合,推进下游
            status_by_id[ne.node_id] = "success"

            for downstream_id in plan.downstream_node_ids:
                down_plan = plans.get(downstream_id)
                if down_plan is None:
                    continue
                # 所有上游都已成功 → 可入队
                if all(status_by_id.get(up) == "success" for up in down_plan.upstream_node_ids):
                    down_ne = await _get_ne_by_node_id(session, ne.run_id, downstream_id)
                    if down_ne is None or down_ne.status != "queued":
                        continue
                    # 合并所有上游节点的 artifact_paths → 下游节点的 inputs
                    # 关键：使用 {upstream_node_id}.{output_name} 作为 key 避免同名覆盖
                    upstream_artifacts: dict[str, str] = {}
                    for upstream_id in down_plan.upstream_node_ids:
                        up_ne = await _get_ne_by_node_id(session, ne.run_id, upstream_id)
                        if up_ne and up_ne.artifact_paths:
                            for output_name, storage_key in up_ne.artifact_paths.items():
                                upstream_artifacts[f"{upstream_id}.{output_name}"] = storage_key
                    if upstream_artifacts:
                        down_ne.artifact_paths = upstream_artifacts
                    await session.commit()
                    run_node.apply_async(
                        args=[str(down_ne.node_exec_id)],
                        queue="nodes-general",
                    )

            # 检查 Run 是否完成
            all_statuses = [n.status for n in all_ne]
            run_completed = all(s in ("success", "cached_hit", "skipped") for s in all_statuses)
            run_failed_any = any(s == "failed" for s in all_statuses)
            if run_completed:
                run.status = "success"
                run.finished_at = datetime.utcnow()
                _log.info(
                    "run_completed",
                    run_id=str(run.run_id),
                    duration_sec=_calc_duration(run.started_at, run.finished_at),
                )

            await session.commit()

            # 推送 WebSocket 事件（commit 后再发布，避免消费者读旧状态）
            await publish_event(
                run.run_id, "node_execution",
                node_id=ne.node_id,
                node_type=ne.node_type,
                status=ne.status,
                output_hash=ne.output_hash,
                artifact_keys=list(ne.artifact_paths.keys()) if ne.artifact_paths else [],
            )
            if run_completed:
                await publish_event(
                    run.run_id, "run_status",
                    status=run.status,
                    duration_sec=_calc_duration(run.started_at, run.finished_at),
                    total_nodes=len(all_ne),
                )
            elif run_failed_any:
                # 部分失败但未完全失败：状态保持 running，不单独推送 run_status
                pass

    @staticmethod
    async def handle_node_failure(
        node_exec_id: UUID,
        error_info: dict[str, Any],
        retry: bool = True,
    ) -> None:
        """节点执行失败 — 更新状态、可选重试。

        Args:
            node_exec_id: NodeExecution UUID。
            error_info: 错误信息(dict,会被原样写入 ``node_executions.error``)。
            retry: 是否允许重试(系统错误 → True;4xx 业务错误 → False)。
        """
        from hscredit_studio.executor.tasks import run_node  # 延迟导入

        async with session_scope() as session:
            ne = await session.get(NodeExecution, node_exec_id)
            if ne is None:
                _log.warning("node_exec_not_found", node_exec_id=str(node_exec_id))
                return

            # 可重试且未超过上限
            if retry and ne.retry_count < _MAX_RETRIES and not error_info.get("non_retryable"):
                ne.retry_count += 1
                ne.status = "failed_retry"
                ne.error = error_info
                await session.commit()
                _log.warning(
                    "node_retry",
                    node_exec_id=str(node_exec_id),
                    retry_count=ne.retry_count,
                    max_retries=_MAX_RETRIES,
                )
                # 指数退避: 2s, 4s, 8s
                run_node.apply_async(
                    args=[str(node_exec_id)],
                    queue="nodes-general",
                    countdown=2 ** ne.retry_count,
                )
                # 推送 retry 事件
                await publish_event(
                    ne.run_id, "node_execution",
                    node_id=ne.node_id,
                    node_type=ne.node_type,
                    status=ne.status,
                    retry_count=ne.retry_count,
                    error_code=error_info.get("code"),
                    error_message=error_info.get("message"),
                )
                return

            # 不可恢复 → 终态 failed
            ne.status = "failed"
            ne.finished_at = datetime.utcnow()
            ne.error = error_info

            run = await session.get(Run, ne.run_id)
            if run is not None:
                run.status = "failed"
                run.finished_at = datetime.utcnow()
                run.error = error_info

            await session.commit()
            _log.error(
                "run_failed",
                node_exec_id=str(node_exec_id),
                node_type=ne.node_type,
                error=error_info,
            )
            # 推送失败事件
            run_id = ne.run_id
            await publish_event(
                run_id, "node_execution",
                node_id=ne.node_id,
                node_type=ne.node_type,
                status=ne.status,
                error_code=error_info.get("code"),
                error_message=error_info.get("message"),
            )
            if run is not None:
                await publish_event(
                    run_id, "run_status",
                    status=run.status,
                    error_code=error_info.get("code"),
                )


# ===== 内部辅助函数 =====


async def _get_ne_by_node_id(
    session: AsyncSession,
    run_id: UUID,
    node_id: str,
) -> NodeExecution | None:
    """按 ``node_id`` 查 ``NodeExecution`` 记录(同 run 内唯一)."""
    return await session.scalar(
        select(NodeExecution).where(
            NodeExecution.run_id == run_id,
            NodeExecution.node_id == node_id,
        )
    )


def _calc_duration(start: datetime | None, end: datetime | None) -> int | None:
    """计算运行时长(秒). 任意一端为 None 时返回 None.

    兼容 naive / aware datetime：统一 strip tzinfo 后用 Unix 时间戳相减。
    """
    if start is None or end is None:
        return None
    try:
        if start.tzinfo is not None:
            start_ts = start.timestamp()
        else:
            start_ts = _naive_to_utc_ts(start)
        if end.tzinfo is not None:
            end_ts = end.timestamp()
        else:
            end_ts = _naive_to_utc_ts(end)
        return int(end_ts - start_ts)
    except Exception:
        return None


def _naive_to_utc_ts(dt: datetime) -> float:
    """把 naive datetime 视为 UTC 转为 Unix 时间戳."""
    return dt.replace(tzinfo=timezone.utc).timestamp()


# 兼容导出:让 task 模块可以显式引用
__all__ = ["RunCoordinator"]


# 旧 import 路径兼容(被注释掉的代码可能还在引用)
_ = NodeExecutionError  # 防止 import 顺序问题导致的运行时错误