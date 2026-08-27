"""Run 执行 API 路由.

提供工作流执行（Run）与节点执行（NodeExecution）相关端点。

路由前缀：``/api/v1/{tenant_slug}/runs`` + 工作流子资源
``/api/v1/{tenant_slug}/workflows/{workflow_id}/runs``
（见 ``main.py``）。

注意：

- 提交 Run 返回 ``202 Accepted`` — 表示已入队等待执行，不是同步完成。
- Run 状态机：``pending → running → (success/cancelled/failed)``；
  ``cached`` 为缓存命中后的特殊终态。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep
from hscredit_studio.schemas.common import PaginatedResponse
from hscredit_studio.schemas.run import (
    ArtifactListResponse,
    NodeExecutionListItem,
    NodeExecutionResponse,
    NodeRetryResponse,
    RunCancelResponse,
    RunListItem,
    RunResponse,
)
from hscredit_studio.services import run as run_service

router = APIRouter(tags=["运行"])


# ===== Run 列表 / 详情 =====


@router.get(
    "",
    response_model=PaginatedResponse[RunListItem],
    summary="Run 列表",
    description=("分页列出当前租户的 Run，支持 ``workflow_id`` / ``status`` 过滤，" "按 submitted_at desc 排序"),
)
async def list_runs(
    session: SessionDep,
    tenant_id: TenantDep,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=200, description="每页条数"),
    workflow_id: UUID | None = Query(default=None, description="按工作流过滤"),
    status: str | None = Query(
        default=None,
        pattern=r"^(pending|queued|running|cached|success|failed|cancelled|retrying)$",
        description="按状态过滤",
    ),
) -> PaginatedResponse[RunListItem]:
    items, total = await run_service.list_runs(
        session,
        UUID(tenant_id),
        page=page,
        page_size=page_size,
        workflow_id=workflow_id,
        status=status,
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return PaginatedResponse[RunListItem](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{run_id}",
    response_model=RunResponse,
    summary="Run 详情",
    description="获取 Run 详情（含 metrics / manifest / error / 节点执行数）",
)
async def get_run(
    run_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
) -> RunResponse:
    return await run_service.get_run(session, UUID(tenant_id), run_id)


# ===== NodeExecution =====


@router.get(
    "/{run_id}/node-executions",
    response_model=list[NodeExecutionListItem],
    summary="Run 的节点执行列表",
    description="列出 Run 的所有节点执行记录（按 created_at asc）",
)
async def list_node_executions(
    run_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
) -> list[NodeExecutionListItem]:
    return await run_service.list_node_executions(session, UUID(tenant_id), run_id)


@router.get(
    "/{run_id}/node-executions/{node_exec_id}",
    response_model=NodeExecutionResponse,
    summary="节点执行详情",
    description="获取单个节点执行的完整详情（含参数快照、产物路径、日志条数）",
)
async def get_node_execution(
    run_id: UUID,
    node_exec_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
) -> NodeExecutionResponse:
    return await run_service.get_node_execution(session, UUID(tenant_id), run_id, node_exec_id)


# ===== 产物 =====


@router.get(
    "/{run_id}/artifacts",
    response_model=ArtifactListResponse,
    summary="Run 的产物列表",
    description=(
        "聚合 Run 所有节点产物的元数据（artifact_type / size / sha256 / "
        "所属节点 / output_name），并为每个产物生成 1 小时有效的预签名下载 URL。"
    ),
)
async def list_artifacts(
    run_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
    include_download_url: bool = Query(
        default=True,
        description="是否生成预签名下载 URL（默认 true）",
    ),
    expires_in: int = Query(
        default=3600,
        ge=60,
        le=86400,
        description="预签名 URL 有效期（秒）",
    ),
) -> ArtifactListResponse:
    return await run_service.list_run_artifacts(
        session,
        UUID(tenant_id),
        run_id,
        include_download_url=include_download_url,
        expires_in=expires_in,
    )


# ===== Run 控制 =====


@router.post(
    "/{run_id}/cancel",
    response_model=RunCancelResponse,
    summary="取消 Run",
    description=(
        "取消处于 ``pending`` / ``queued`` / ``running`` / ``retrying`` 状态的 Run，"
        "同步取消所有未终态的 NodeExecution"
    ),
)
async def cancel_run(
    run_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
) -> RunCancelResponse:
    run = await run_service.cancel_run(session, UUID(tenant_id), run_id)
    return RunCancelResponse(
        run_id=run.id,
        status=run.status,
        cancelled_at=run.finished_at or run.updated_at,
        message="Run 已取消",
    )


# ===== Node 重试 =====


@router.post(
    "/{run_id}/node-executions/{node_exec_id}/retry",
    response_model=NodeRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="重试单个节点",
    description=(
        "仅当节点终态为 ``failed`` 时可重试；"
        "系统会重置 ``status='queued'`` / ``retry_count=0`` / ``error=null`` 并"
        "重新入 Celery 队列 ``nodes-general``。"
        "重试会保留上游已成功节点产物的 artifact_paths 作为输入。"
    ),
)
async def retry_node_execution(
    run_id: UUID,
    node_exec_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
) -> NodeRetryResponse:
    user_id = UUID(user["sub"])
    return await run_service.retry_node_execution(
        session,
        UUID(tenant_id),
        user_id,
        run_id,
        node_exec_id,
    )


__all__ = ["router"]
