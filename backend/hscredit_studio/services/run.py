"""Run 提交 / 取消 / 查询服务.

提供 Run 生命周期相关业务逻辑：

- 提交 Run（创建 run + 所有 node_executions 记录）
- Run 列表 / 详情
- Run 取消（state machine 校验）
- NodeExecution 列表 / 详情
- Run 编号自增（per-workflow 单调递增）

设计要点（见 ``docs/design/09-database-design.md`` 第 9.3.3 节 + 业务流文档）：

- ``Run.status`` 取值与 ORM ``RUN_STATUS_VALUES`` 对齐
  （``pending`` / ``queued`` / ``running`` / ``success`` / ``failed`` /
  ``cancelled`` / ``cached``），可取消的状态为 ``pending`` / ``queued`` /
  ``running`` / ``retrying``。
- ``NodeExecution.status`` 由 executor（Phase 1.5）驱动更新；
  本 service 仅创建 ``pending`` 占位记录。
- ``Run.workflow_version_number`` 是冗余字段，UI 显示用，
  提交时从 ``WorkflowVersion.version_number`` 直接拷贝。
- ``priority`` / ``notes`` 暂存 ``inputs_snapshot``（ORM 无对应列），
  Phase 2 接入调度器后迁移到独立列。
- 入队（Celery / 任务队列）逻辑在 Phase 1.5（批次 5）实现。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.exceptions import (
    FeatureNotFoundError,
    StateError,
)
from hscredit_studio.executor.coordinator import RunCoordinator
from hscredit_studio.models import (
    NodeArtifact,
    NodeExecution,
    NodeExecutionLog,
    Run,
    Workflow,
    WorkflowVersion,
)
from hscredit_studio.nodes.registry import NodeRegistry
from hscredit_studio.schemas.run import (
    ArtifactListResponse,
    ArtifactResponse,
    NodeExecutionListItem,
    NodeExecutionResponse,
    NodeRetryResponse,
    RunListItem,
    RunResponse,
    RunSubmitRequest,
)
from hscredit_studio.schemas.workflow import WorkflowDefinition
from hscredit_studio.services.storage import presigned_download_url

# 可取消的 Run 状态（包含 ``retrying`` 用于支持重试中取消）
_CANCELLABLE_RUN_STATES = ("pending", "queued", "running", "retrying")


# ===== 提交 =====


async def submit_run(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    workflow_id: UUID,
    req: RunSubmitRequest,
) -> RunResponse:
    """提交 Run — 创建 run 记录 + 所有 node_executions（pending）占位.

    Returns
    -------
    RunResponse
        新建 Run 的完整响应。

    Raises
    ------
    FeatureNotFoundError
        工作流不存在 / 已软删除 / 指定的 version_id 不属于该 workflow。
    StateError
        工作流没有可用版本（从未保存过定义）。

    Notes
    -----
    Phase 1 仅创建 DB 记录；Phase 1.5（批次 5）将在 ``executor.coordinator``
    中实现真正的入队逻辑。当前 ``run.status`` 写入 ``"queued"``。
    """
    wf = await session.scalar(
        select(Workflow).where(
            Workflow.workflow_id == workflow_id,
            Workflow.tenant_id == tenant_id,
            Workflow.deleted_at.is_(None),
        )
    )
    if wf is None:
        raise FeatureNotFoundError(f"工作流 {workflow_id} 不存在")

    # 选版本：显式指定 or 回退到 current_version_id
    if req.workflow_version_id is not None:
        version = await session.get(WorkflowVersion, req.workflow_version_id)
        if version is None or version.workflow_id != workflow_id:
            raise FeatureNotFoundError(f"指定的版本 {req.workflow_version_id} 不存在或不属于该工作流")
    else:
        if wf.current_version_id is None:
            raise StateError("工作流没有可用版本，无法提交 Run")
        version = await session.get(WorkflowVersion, wf.current_version_id)
        if version is None:
            raise StateError("工作流的 HEAD 版本不存在或已删除")

    # run_number 自增（per-tenant 唯一，含已删除 run 以保持 gap-free 失败追溯）
    last_run = await session.scalar(
        select(func.coalesce(func.max(Run.run_number), 0)).where(Run.tenant_id == tenant_id)
    )
    next_run_number = (last_run or 0) + 1

    # 将 priority / notes 一并存入 inputs_snapshot
    inputs_snapshot: dict[str, Any] = dict(req.inputs_snapshot or {})
    inputs_snapshot.setdefault("priority", req.priority)
    if req.notes:
        inputs_snapshot.setdefault("notes", req.notes)

    now = datetime.utcnow()
    run = Run(
        tenant_id=tenant_id,
        workflow_id=workflow_id,
        workflow_version_id=version.version_id,
        workflow_version_number=version.version_number,
        run_number=next_run_number,
        status="queued",
        submitted_by=user_id,
        submitted_at=now,
        inputs_snapshot=inputs_snapshot,
    )
    session.add(run)
    await session.flush()

    # 为 workflow 中每个节点创建 NodeExecution 占位记录（status=queued）
    # definition 字段在 ORM 端是 JSONB dict，直接 from version.definition 即可
    definition = WorkflowDefinition(**version.definition)
    for node in definition.nodes:
        ne = NodeExecution(
            run_id=run.run_id,
            tenant_id=tenant_id,
            node_id=node.id,
            node_type=node.type,
            status="queued",
            queued_at=now,
            params=node.data or {},
        )
        session.add(ne)

    await session.commit()

    # 入 Celery 队列（协调器自行读取 WorkflowVersion.definition 并派发入度=0 节点）
    await RunCoordinator.enqueue_initial_nodes(run.run_id)

    # 审计: Run 提交
    from hscredit_studio.services import audit as audit_service

    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        action=audit_service.AuditAction.WORKFLOW_RUN_SUBMIT,
        resource_type=audit_service.ResourceType.RUN,
        resource_id=run.run_id,
        details={
            "workflow_id": str(workflow_id),
            "run_number": run.run_number,
            "priority": req.priority,
            "notes": req.notes,
        },
    )
    await session.commit()

    return await get_run(session, tenant_id, run.run_id)


# ===== 列表 =====


async def list_runs(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
    workflow_id: UUID | None = None,
    status: str | None = None,
) -> tuple[list[RunListItem], int]:
    """分页列出 Run（按 tenant_id 隔离，可选 workflow_id / status 过滤）."""
    base = select(Run).where(Run.tenant_id == tenant_id)
    count_q = select(func.count()).select_from(Run).where(Run.tenant_id == tenant_id)

    if workflow_id is not None:
        base = base.where(Run.workflow_id == workflow_id)
        count_q = count_q.where(Run.workflow_id == workflow_id)
    if status is not None:
        base = base.where(Run.status == status)
        count_q = count_q.where(Run.status == status)

    base = base.order_by(Run.submitted_at.desc()).offset((page - 1) * page_size).limit(page_size)

    runs = (await session.scalars(base)).all()
    total = (await session.scalar(count_q)) or 0

    items = [_to_run_list_item(r) for r in runs]
    return items, total


# ===== 详情 =====


async def get_run(
    session: AsyncSession,
    tenant_id: UUID,
    run_id: UUID,
) -> RunResponse:
    """获取 Run 详情（含 metrics / manifest / error / node_executions 计数）."""
    r = await session.get(Run, run_id)
    if r is None or r.tenant_id != tenant_id:
        raise FeatureNotFoundError(f"Run {run_id} 不存在")

    ne_count = (
        await session.scalar(select(func.count()).select_from(NodeExecution).where(NodeExecution.run_id == run_id)) or 0
    )

    duration_seconds = float(r.duration_sec) if r.duration_sec is not None else None

    return RunResponse(
        id=r.run_id,
        workflow_id=r.workflow_id,
        workflow_version_id=r.workflow_version_id,
        run_number=r.run_number,
        status=r.status,
        submitted_by=r.submitted_by,
        submitted_at=r.submitted_at,
        started_at=r.started_at,
        finished_at=r.finished_at,
        duration_seconds=duration_seconds,
        progress=0.0,  # 由前端按 node_executions 计算
        error_summary=(r.error or {}).get("message") if r.error else None,
        inputs_snapshot=r.inputs_snapshot or {},
        metrics=r.metrics or {},
        manifest=r.manifest or {},
        error=r.error,
        node_executions_count=ne_count,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


# ===== 取消 =====


async def cancel_run(
    session: AsyncSession,
    tenant_id: UUID,
    run_id: UUID,
) -> RunResponse:
    """取消 Run（仅 ``pending`` / ``queued`` / ``running`` / ``retrying`` 可取消）.

    终态 (``success`` / ``failed`` / ``cancelled`` / ``cached``) 不允许取消，
    抛 :class:`StateError` (HTTP 409)。
    """
    r = await session.get(Run, run_id)
    if r is None or r.tenant_id != tenant_id:
        raise FeatureNotFoundError(f"Run {run_id} 不存在")

    if r.status not in _CANCELLABLE_RUN_STATES:
        raise StateError(
            f"Run 状态为 {r.status}，无法取消",
            details={"run_id": str(run_id), "current_status": r.status},
        )

    now = datetime.utcnow()
    r.status = "cancelled"
    r.finished_at = now
    # 计算 duration_sec（按 started_at 计算；未启动则 None）
    if r.started_at is not None:
        r.duration_sec = int((now - r.started_at).total_seconds())

    # 同步取消所有未终态的 NodeExecution
    active_ne_states = ("pending", "queued", "running", "retrying")
    active_nes = (
        await session.scalars(
            select(NodeExecution).where(
                NodeExecution.run_id == run_id,
                NodeExecution.status.in_(active_ne_states),
            )
        )
    ).all()
    for ne in active_nes:
        ne.status = "cancelled"
        ne.finished_at = now
        if ne.started_at is not None:
            ne.duration_sec = int((now - ne.started_at).total_seconds())

    await session.commit()

    # TODO(Phase 1.5 / 批次 5): 通知 Celery worker 停止当前任务
    # await RunCoordinator(session).cancel_running_tasks(run_id)

    return await get_run(session, tenant_id, run_id)


# ===== NodeExecution =====


async def list_node_executions(
    session: AsyncSession,
    tenant_id: UUID,
    run_id: UUID,
) -> list[NodeExecutionListItem]:
    """列出 Run 的所有节点执行（按 created_at asc）."""
    r = await session.get(Run, run_id)
    if r is None or r.tenant_id != tenant_id:
        raise FeatureNotFoundError(f"Run {run_id} 不存在")

    nes = (
        await session.scalars(
            select(NodeExecution).where(NodeExecution.run_id == run_id).order_by(NodeExecution.created_at)
        )
    ).all()

    return [_to_node_list_item(ne) for ne in nes]


async def get_node_execution(
    session: AsyncSession,
    tenant_id: UUID,
    run_id: UUID,
    node_exec_id: UUID,
) -> NodeExecutionResponse:
    """获取单个节点执行详情（含日志条数计数）."""
    r = await session.get(Run, run_id)
    if r is None or r.tenant_id != tenant_id:
        raise FeatureNotFoundError(f"Run {run_id} 不存在")

    ne = await session.get(NodeExecution, node_exec_id)
    if ne is None or ne.run_id != run_id:
        raise FeatureNotFoundError(f"Node execution {node_exec_id} 不存在")

    logs_count = (
        await session.scalar(
            select(func.count()).select_from(NodeExecutionLog).where(NodeExecutionLog.node_exec_id == node_exec_id)
        )
        or 0
    )

    duration_seconds = float(ne.duration_sec) if ne.duration_sec is not None else None
    return NodeExecutionResponse(
        id=ne.node_exec_id,
        run_id=ne.run_id,
        node_id=ne.node_id,
        node_type=ne.node_type,
        status=ne.status,
        retry_count=ne.retry_count,
        started_at=ne.started_at,
        finished_at=ne.finished_at,
        duration_seconds=duration_seconds,
        cached_from_run_id=ne.cached_from_run_id,
        input_hash=ne.input_hash,
        output_hash=ne.output_hash,
        params=ne.params or {},
        artifact_paths=_artifact_paths_to_list(ne.artifact_paths),
        error=ne.error,
        logs_count=logs_count,
        created_at=ne.created_at,
        updated_at=ne.started_at or ne.created_at,
    )


# ===== 内部辅助 =====


def _to_run_list_item(r: Run) -> RunListItem:
    """ORM Run → RunListItem."""
    duration_seconds = float(r.duration_sec) if r.duration_sec is not None else None
    return RunListItem(
        id=r.run_id,
        workflow_id=r.workflow_id,
        workflow_version_id=r.workflow_version_id,
        run_number=r.run_number,
        status=r.status,
        submitted_by=r.submitted_by,
        submitted_at=r.submitted_at,
        started_at=r.started_at,
        finished_at=r.finished_at,
        duration_seconds=duration_seconds,
        progress=0.0,
        error_summary=(r.error or {}).get("message") if r.error else None,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _to_node_list_item(ne: NodeExecution) -> NodeExecutionListItem:
    """ORM NodeExecution → NodeExecutionListItem."""
    duration_seconds = float(ne.duration_sec) if ne.duration_sec is not None else None
    return NodeExecutionListItem(
        id=ne.node_exec_id,
        run_id=ne.run_id,
        node_id=ne.node_id,
        node_type=ne.node_type,
        status=ne.status,
        retry_count=ne.retry_count,
        started_at=ne.started_at,
        finished_at=ne.finished_at,
        duration_seconds=duration_seconds,
        cached_from_run_id=ne.cached_from_run_id,
        created_at=ne.created_at,
        updated_at=ne.started_at or ne.created_at,
    )


def _artifact_paths_to_list(artifact_paths: Any) -> list[str]:
    """ORM ``artifact_paths`` 实际为 dict，转换为 UI 友好的 list[str].

    容错处理：None → [], dict → list(dict.keys())，list → 原样返回。
    """
    if artifact_paths is None:
        return []
    if isinstance(artifact_paths, list):
        return [str(p) for p in artifact_paths]
    if isinstance(artifact_paths, dict):
        return [str(k) for k in artifact_paths]
    return [str(artifact_paths)]


__all__ = [
    "cancel_run",
    "get_node_execution",
    "get_run",
    "list_node_executions",
    "list_run_artifacts",
    "list_runs",
    "retry_node_execution",
    "submit_run",
]


# ===== 产物列表 =====


async def list_run_artifacts(
    session: AsyncSession,
    tenant_id: UUID,
    run_id: UUID,
    *,
    include_download_url: bool = True,
    expires_in: int = 3600,
) -> ArtifactListResponse:
    """列出 Run 的所有节点产物（含预签名下载 URL）。

    数据来源：
        - ``node_artifacts`` 表（每个产物一行，含 sha256/size/type/path）
        - ``node_executions`` 表（关联 ``node_id`` / ``node_type`` /
          ``artifact_paths`` 用于反查 output_name）

    输出顺序：先按 ``node_executions.created_at``、再按 ``artifact_type``、
    最后按 ``node_artifacts.created_at``，便于前端按节点分组渲染。

    设计要点：

    1. ``NodeArtifact`` 表不存 ``output_name``，仅存 ``storage_path``。通过
       ``NodeExecution.artifact_paths``（dict[output_name, storage_path]）反查
       即可还原产物与输出端口名的对应关系。
    2. 预签名 URL 默认 1 小时有效；调用方可通过 ``expires_in`` 自定义。
    3. 同一 ``storage_path`` 被多个 output 共享时（如 WOE 同时输出 ``woe_features``
       和 ``selected_df``），仅产生 1 行 NodeArtifact；这里只展示这一行并把找到
       的第一个 output_name 填入，便于 UI 显示。
    """
    r = await session.get(Run, run_id)
    if r is None or r.tenant_id != tenant_id:
        raise FeatureNotFoundError(f"Run {run_id} 不存在")

    # 1) 拉所有 NodeExecution，构造 node_exec_id -> NodeExecution 索引
    nes = (
        await session.scalars(
            select(NodeExecution).where(NodeExecution.run_id == run_id).order_by(NodeExecution.created_at)
        )
    ).all()
    ne_by_id: dict[UUID, NodeExecution] = {ne.node_exec_id: ne for ne in nes}

    # 2) 拉所有 NodeArtifact
    artifacts = (
        await session.scalars(
            select(NodeArtifact)
            .where(NodeArtifact.node_exec_id.in_(list(ne_by_id.keys()) or [UUID(int=0)]))
            .order_by(NodeArtifact.created_at)
        )
    ).all()

    # 3) 构造 NodeType -> Contract.name 缓存（用于显示中文节点名）
    name_by_type: dict[str, str] = {}
    for ne in nes:
        if ne.node_type not in name_by_type:
            cls = NodeRegistry.try_get(ne.node_type)
            if cls is not None:
                name_by_type[ne.node_type] = cls.contract.name
            else:
                name_by_type[ne.node_type] = ne.node_type

    # 4) 组装响应
    out: list[ArtifactResponse] = []
    for art in artifacts:
        ne = ne_by_id.get(art.node_exec_id)
        if ne is None:
            continue

        # 反查 output_name：NodeExecution.artifact_paths 是 dict[output_name, storage_path]
        output_name: str | None = None
        if isinstance(ne.artifact_paths, dict):
            for oname, spath in ne.artifact_paths.items():
                if spath == art.storage_path:
                    output_name = str(oname)
                    break

        # 预签名 URL（异步）
        dl_url: str | None = None
        if include_download_url:
            try:
                dl_url = await presigned_download_url(
                    tenant_id=tenant_id,
                    key=art.storage_path,
                    expires_in=expires_in,
                )
            except Exception:
                # 签名失败不影响主流程；前端看到 download_url=null 时显示「不可下载」
                dl_url = None

        out.append(
            ArtifactResponse(
                id=art.artifact_id,
                artifact_type=art.artifact_type,  # type: ignore[arg-type]
                storage_path=art.storage_path,
                size_bytes=art.size_bytes or 0,
                sha256=art.sha256,
                metadata=art.metadata_ or {},
                download_url=dl_url,
                node_id=ne.node_id,
                node_type=ne.node_type,
                node_name=name_by_type.get(ne.node_type, ne.node_type),
                output_name=output_name,
                created_at=art.created_at,
            )
        )

    return ArtifactListResponse(artifacts=out)


# ===== 节点重试 =====


async def retry_node_execution(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    run_id: UUID,
    node_exec_id: UUID,
) -> NodeRetryResponse:
    """重试一个失败的 NodeExecution.

    业务规则：

    - 仅当 ``ne.status == 'failed'`` 时可重试；其他状态（running / success /
      cached_hit / queued 等）抛 :class:`StateError`。
    - 重置：``status='queued'``、``retry_count=0``、``error=null``、清空
      ``finished_at``、``output_hash``、``artifact_paths``。
    - 如果 Run 当前状态为 ``failed``，同步将 Run 重置为 ``running``（因为失败
      节点即将重新执行）；否则保留原状态。
    - 重新入 Celery 队列 ``nodes-general``；上游节点的 artifact_paths 已在
      NodeExecution 记录中保留，无需重新加载。

    Returns:
        :class:`NodeRetryResponse` 包含新状态与中文描述。
    """
    from hscredit_studio.executor.tasks import run_node  # 延迟避免循环

    # 1. 校验 Run 存在 + 租户隔离
    run = await session.get(Run, run_id)
    if run is None or run.tenant_id != tenant_id:
        raise FeatureNotFoundError(f"Run {run_id} 不存在")

    # 2. 校验 NodeExecution
    ne = await session.get(NodeExecution, node_exec_id)
    if ne is None or ne.run_id != run_id:
        raise FeatureNotFoundError(f"Node execution {node_exec_id} 不存在")
    if ne.status != "failed":
        raise StateError(
            f"节点 {ne.node_id} 当前状态为 {ne.status}，仅 failed 状态可重试",
            details={"current_status": ne.status, "node_id": ne.node_id},
        )

    # 3. 重置 NE 状态
    ne.status = "queued"
    ne.retry_count = 0
    ne.error = None
    ne.finished_at = None
    ne.output_hash = None
    ne.artifact_paths = None

    # 4. 如 Run 已 failed → 改回 running（让前端知道又活了）
    if run.status == "failed":
        run.status = "running"
        run.finished_at = None
        run.error = None

    await session.commit()

    # 5. 重新入队
    run_node.apply_async(args=[str(node_exec_id)], queue="nodes-general")

    # 6. 审计: 节点重试
    from hscredit_studio.services import audit as audit_service

    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        action=audit_service.AuditAction.WORKFLOW_RUN_RETRY_NODE,
        resource_type=audit_service.ResourceType.NODE_EXECUTION,
        resource_id=ne.node_exec_id,
        details={
            "run_id": str(run.run_id),
            "node_id": ne.node_id,
            "node_type": ne.node_type,
        },
    )
    await session.commit()

    return NodeRetryResponse(
        node_exec_id=ne.node_exec_id,
        run_id=run.run_id,
        status=ne.status,
        message=f"节点 {ne.node_id} 已重新入队（操作者 {user_id}）",
    )
