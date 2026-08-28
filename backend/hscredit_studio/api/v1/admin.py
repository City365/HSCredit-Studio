"""租户超管后台 API — Phase 6 B29.

依据 docs/ROADMAP.md Phase 6 B29:

| 端点 | 方法 | 用途 |
|---|---|---|
| /admin/overview | GET | 全平台跨租户仪表板 |
| /admin/tenants | GET | 租户列表 (搜索/过滤/分页) |
| /admin/tenants/{tenant_id} | GET | 租户详情 (成员/用量/趋势/审计) |
| /admin/tenants/{tenant_id}/status | POST | 启用/停用/归档 |
| /admin/tenants/{tenant_id}/migrate | POST | 迁移到目标集群 |
| /admin/tenants/{tenant_id}/users/{user_id}/role | POST | 修改用户角色 (审计) |

所有端点均需 ``super_admin`` 角色 (B28 RBAC 强制).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status

from hscredit_studio.api.deps import CurrentUserDep, require_role
from hscredit_studio.schemas.admin import (
    GlobalOverviewResponse,
    RoleChangeRequest,
    RoleChangeResponse,
    TenantAuditEventInfo,
    TenantDetailResponse,
    TenantListItem,
    TenantListResponse,
    TenantMemberInfo,
    TenantMigrateRequest,
    TenantMigrateResponse,
    TenantOverviewItem,
    TenantStatusUpdateRequest,
    TenantStatusUpdateResponse,
    TenantTrendPoint,
    TenantUsageInfo,
)
from hscredit_studio.services import admin_console as svc
from hscredit_studio.services.rbac import Role

router = APIRouter(
    tags=["超管后台"],
    dependencies=[Depends(require_role(Role.SUPER_ADMIN))],
)


def _to_overview_item(d: svc.TenantOverview) -> TenantOverviewItem:
    return TenantOverviewItem(
        tenant_id=d.tenant_id,
        slug=d.slug,
        name=d.name,
        plan=d.plan,
        status=d.status,
        member_count=d.member_count,
        total_runs_30d=d.total_runs_30d,
        total_cpu_seconds_30d=d.total_cpu_seconds_30d,
        last_active_at=d.last_active_at,
        is_healthy=d.is_healthy,
    )


@router.get(
    "/overview",
    summary="全平台跨租户概览 (B29 验收)",
    response_model=GlobalOverviewResponse,
)
async def get_overview(_: CurrentUserDep) -> GlobalOverviewResponse:
    """super_admin 仪表板顶层 — 全平台聚合指标 + Top 10 租户."""
    g = await svc.get_global_overview()
    return GlobalOverviewResponse(
        total_tenants=g.total_tenants,
        active_tenants=g.active_tenants,
        suspended_tenants=g.suspended_tenants,
        archived_tenants=g.archived_tenants,
        total_members=g.total_members,
        total_runs_30d=g.total_runs_30d,
        total_cpu_seconds_30d=g.total_cpu_seconds_30d,
        top_tenants_by_runs=[_to_overview_item(t) for t in g.top_tenants_by_runs],
        plan_distribution=g.plan_distribution,
        generated_at=g.generated_at,
    )


@router.get(
    "/tenants",
    summary="租户列表 (B29)",
    response_model=TenantListResponse,
)
async def list_all_tenants(
    _: CurrentUserDep,
    search: str | None = Query(None, description="按 name/slug 模糊"),
    status_filter: str | None = Query(None, alias="status", description="active/suspended/archived"),
    plan_filter: str | None = Query(None, alias="plan", description="free/pro/enterprise"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> TenantListResponse:
    """跨租户列表 — 搜索 / 过滤 / 分页."""
    data = await svc.list_tenants(
        search=search,
        status_filter=status_filter,
        plan_filter=plan_filter,
        page=page,
        page_size=page_size,
    )
    return TenantListResponse(
        items=[TenantListItem(**it) for it in data["items"]],
        total=data["total"],
        page=data["page"],
        page_size=data["page_size"],
    )


@router.get(
    "/tenants/{tenant_id}",
    summary="租户详情 (B29)",
    response_model=TenantDetailResponse,
)
async def get_one_tenant(
    _: CurrentUserDep,
    tenant_id: UUID = Path(...),
) -> TenantDetailResponse:
    """返回完整租户详情: 基本信息 + 成员 + 用量 + 30 天趋势 + 最近审计."""
    try:
        d = await svc.get_tenant_detail(tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "E_NOT_FOUND", "message": str(e)}) from e

    return TenantDetailResponse(
        tenant_id=d["tenant_id"],
        slug=d["slug"],
        name=d["name"],
        plan=d["plan"],
        status=d["status"],
        settings=d["settings"],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
        members=[TenantMemberInfo(**m) for m in d["members"]],
        usage_30d=TenantUsageInfo(**d["usage_30d"]),
        usage_trend_30d=[TenantTrendPoint(**t) for t in d["usage_trend_30d"]],
        recent_audit_events=[
            TenantAuditEventInfo(**ev) for ev in d["recent_audit_events"]
        ],
    )


@router.post(
    "/tenants/{tenant_id}/status",
    summary="启用/停用/归档 (B29)",
    response_model=TenantStatusUpdateResponse,
)
async def update_tenant_status(
    _: CurrentUserDep,
    tenant_id: UUID = Path(...),
    body: TenantStatusUpdateRequest = Body(...),
) -> TenantStatusUpdateResponse:
    """更新租户状态 (active/suspended/archived)."""
    try:
        t = await svc.set_tenant_status(tenant_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "E_BAD_REQUEST", "message": str(e)}) from e
    return TenantStatusUpdateResponse(
        tenant_id=t.tenant_id, status=t.status, updated_at=t.updated_at,
    )


@router.post(
    "/tenants/{tenant_id}/migrate",
    summary="迁移到目标集群 (B29)",
    response_model=TenantMigrateResponse,
)
async def migrate_tenant_endpoint(
    _: CurrentUserDep,
    tenant_id: UUID = Path(...),
    body: TenantMigrateRequest = Body(...),
) -> TenantMigrateResponse:
    """将租户标记为目标集群. 实际迁移由运维脚本执行."""
    try:
        t = await svc.migrate_tenant(tenant_id, body.target_cluster)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "E_BAD_REQUEST", "message": str(e)}) from e
    return TenantMigrateResponse(
        tenant_id=t.tenant_id,
        target_cluster=t.settings["cluster"],
        migrated_at=t.settings["migrated_at"],
    )


@router.post(
    "/tenants/{tenant_id}/users/{user_id}/role",
    summary="修改用户角色 (B29 + B28 联动)",
    response_model=RoleChangeResponse,
)
async def change_role(
    user: CurrentUserDep,
    tenant_id: UUID = Path(...),
    user_id: UUID = Path(...),
    body: RoleChangeRequest = Body(...),
) -> RoleChangeResponse:
    """修改租户成员的角色, 写入 ``user_role_audit`` (PIPL 留痕)."""
    changed_by = UUID(user["sub"])
    try:
        m = await svc.change_user_role(
            tenant_id=tenant_id,
            user_id=user_id,
            new_role=body.new_role,
            changed_by=changed_by,
            reason=body.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "E_BAD_REQUEST", "message": str(e)}) from e
    return RoleChangeResponse(
        tenant_id=m.tenant_id,
        user_id=m.user_id,
        old_role=m.role,
        new_role=m.role,
        changed_by=changed_by,
        changed_at=m.updated_at,
    )


__all__ = ["router"]
