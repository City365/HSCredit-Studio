"""工作流 API 路由.

提供工作流 CRUD、版本管理、导入导出等端点。

路由前缀：``/api/v1/{tenant_slug}/workflows``（见 ``main.py``）。
所有端点均需鉴权（``CurrentUserDep``）+ 租户隔离（``TenantDep``）。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep
from hscredit_studio.schemas.common import PaginatedResponse
from hscredit_studio.schemas.workflow import (
    WorkflowCreate,
    WorkflowExportResponse,
    WorkflowImportRequest,
    WorkflowListItem,
    WorkflowResponse,
    WorkflowUpdate,
    WorkflowVersionCreate,
    WorkflowVersionResponse,
)
from hscredit_studio.schemas.run import RunResponse, RunSubmitRequest
from hscredit_studio.services import run as run_service
from hscredit_studio.services import workflow as wf_service

router = APIRouter(tags=["工作流"])


# ===== CRUD =====


@router.get(
    "",
    response_model=PaginatedResponse[WorkflowListItem],
    summary="工作流列表",
    description="分页列出当前租户的工作流，支持搜索、tag 过滤与排序",
)
async def list_workflows(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,  # noqa: ARG001 — 仅用于鉴权
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=200, description="每页条数"),
    search: str | None = Query(default=None, description="模糊匹配 name / description"),
    tags: list[str] | None = Query(default=None, description="tag 过滤（AND 语义）"),
    sort_by: str = Query(
        default="updated_at",
        description="排序字段（ORM 列名，如 updated_at / created_at / name）",
    ),
    sort_order: str = Query(default="desc", pattern=r"^(asc|desc)$", description="排序方向"),
) -> PaginatedResponse[WorkflowListItem]:
    items, total = await wf_service.list_workflows(
        session,
        UUID(tenant_id),
        page=page,
        page_size=page_size,
        search=search,
        tags=tags,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return PaginatedResponse[WorkflowListItem](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post(
    "",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建工作流",
    description="创建工作流并自动生成 v1 初始版本",
)
async def create_workflow(
    req: WorkflowCreate,
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
) -> WorkflowResponse:
    # JWT payload 中 user_id 存放在 ``sub`` claim
    user_id = UUID(user["sub"])
    return await wf_service.create_workflow(session, UUID(tenant_id), user_id, req)


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="工作流详情",
    description="获取工作流详情（含当前 HEAD 版本定义 + 版本 / 执行计数）",
)
async def get_workflow(
    workflow_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
) -> WorkflowResponse:
    return await wf_service.get_workflow(session, UUID(tenant_id), workflow_id)


@router.patch(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="更新工作流",
    description=(
        "PATCH 语义：字段部分更新；若 ``definition`` 变更则自动创建新版本号 +1"
    ),
)
async def update_workflow(
    workflow_id: UUID,
    req: WorkflowUpdate,
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
) -> WorkflowResponse:
    user_id = UUID(user["sub"])
    return await wf_service.update_workflow(
        session, UUID(tenant_id), user_id, workflow_id, req
    )


@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="软删除工作流",
    description="标记 ``deleted_at``，保留版本历史与执行记录",
)
async def delete_workflow(
    workflow_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
) -> None:
    await wf_service.delete_workflow(session, UUID(tenant_id), workflow_id)


# ===== 版本管理 =====


@router.get(
    "/{workflow_id}/versions",
    response_model=list[WorkflowVersionResponse],
    summary="列出全部版本",
    description="按 version_number desc 返回工作流的全部历史版本",
)
async def list_versions(
    workflow_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
) -> list[WorkflowVersionResponse]:
    return await wf_service.list_versions(session, UUID(tenant_id), workflow_id)


@router.post(
    "/{workflow_id}/versions",
    response_model=WorkflowVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="手动创建新版本",
    description="不通过 PATCH，直接为 workflow 创建一个新版本（自动成为 HEAD）",
)
async def create_version(
    workflow_id: UUID,
    req: WorkflowVersionCreate,
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
) -> WorkflowVersionResponse:
    user_id = UUID(user["sub"])
    return await wf_service.create_version(
        session, UUID(tenant_id), user_id, workflow_id, req
    )


@router.get(
    "/{workflow_id}/versions/{version_number}",
    response_model=WorkflowVersionResponse,
    summary="版本详情",
    description="按版本号获取工作流的指定版本",
)
async def get_version(
    workflow_id: UUID,
    version_number: int,
    session: SessionDep,
    tenant_id: TenantDep,
) -> WorkflowVersionResponse:
    return await wf_service.get_version(
        session, UUID(tenant_id), workflow_id, version_number
    )


# ===== Run 提交 =====


@router.post(
    "/{workflow_id}/runs",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="提交 Run",
    description="异步提交工作流执行：创建 Run + 所有 NodeExecution 占位记录，并入队 Celery 执行",
)
async def submit_run(
    workflow_id: UUID,
    req: RunSubmitRequest,
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
) -> RunResponse:
    user_id = UUID(user["sub"])
    return await run_service.submit_run(
        session, UUID(tenant_id), user_id, workflow_id, req
    )


# ===== 导入 / 导出 =====


@router.get(
    "/{workflow_id}/export",
    response_model=WorkflowExportResponse,
    summary="导出工作流",
    description="导出 workflow + 最新版本为 JSON 包（用于备份 / 迁移 / 模板导入）",
)
async def export_workflow(
    workflow_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
) -> WorkflowExportResponse:
    return await wf_service.export_workflow(session, UUID(tenant_id), workflow_id)


@router.post(
    "/import",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="导入工作流",
    description="从 ``WorkflowExportResponse`` 格式的 JSON 包导入工作流（作为新工作流）",
)
async def import_workflow(
    req: WorkflowImportRequest,
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
) -> WorkflowResponse:
    user_id = UUID(user["sub"])
    return await wf_service.import_workflow(session, UUID(tenant_id), user_id, req.payload)


__all__ = ["router"]