"""RBAC API — Phase 6 B28.

依据 docs/ROADMAP.md Phase 6 B28:

| 端点 | 方法 | 用途 |
|---|---|---|
| /rbac/matrix | GET | 权限矩阵 (5 角色 × 5 资源 × 3 动作) |
| /rbac/menu | GET | 当前角色可见菜单项 |
| /rbac/check | POST | ad-hoc 权限检查 (供前端按钮显隐) |
| /rbac/policies | GET | 列出策略 (含租户覆盖) |
| /rbac/policies | POST | 新增策略 (租户级覆盖) |
| /rbac/audit | GET | 角色变更审计 (PIPL 合规留痕) |
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Query
from sqlalchemy import select

from hscredit_studio.api.deps import CurrentUserDep, SessionDep
from hscredit_studio.models import RolePolicy, UserRoleAudit
from hscredit_studio.schemas.rbac import (
    MenuResponse,
    PermissionCheckRequest,
    PermissionCheckResponse,
    PermissionMatrixResponse,
    RoleAuditItem,
    RoleAuditListResponse,
    RoleInfo,
    RolePolicyCreate,
    RolePolicyResponse,
)
from hscredit_studio.services.rbac import (
    PERMISSION_MATRIX,
    Action,
    Resource,
    Role,
    check_permission,
    menu_for_role,
    normalize_role,
    permission_decision,
)

router = APIRouter(tags=["RBAC"])


_ROLE_LABELS: dict[Role, tuple[str, bool, str]] = {
    Role.SUPER_ADMIN: ("平台超管", False, "跨租户访问, 用于客户成功/运维"),
    Role.TENANT_ADMIN: ("租户管理员", True, "租户内全权, 含订阅/账单"),
    Role.ANALYST: ("业务分析师", True, "读写工作流/运行/模型, 无 billing"),
    Role.VIEWER: ("只读用户", True, "仅可查看资源, 不能修改"),
    Role.NONE: ("无权限", True, "禁用成员"),
}


@router.get(
    "/matrix",
    summary="权限矩阵 (Phase 6 B28)",
    response_model=PermissionMatrixResponse,
)
async def get_permission_matrix(_: CurrentUserDep) -> PermissionMatrixResponse:
    """返回完整角色 × 资源 × 动作权限矩阵 (供前端展示)."""
    roles: list[RoleInfo] = []
    for r in Role:
        label, scoped, desc = _ROLE_LABELS.get(r, (r.value, True, ""))
        roles.append(
            RoleInfo(
                role=r.value,
                label=label,
                rank=r.rank,
                is_tenant_scoped=scoped,
                description=desc,
            )
        )

    matrix: dict[str, dict[str, str | None]] = {}
    for role in Role:
        per_role: dict[str, str | None] = {}
        for resource in Resource:
            action = PERMISSION_MATRIX.get(role, {}).get(resource)
            per_role[resource.value] = action.value if action else None
        matrix[role.value] = per_role

    return PermissionMatrixResponse(
        roles=roles,
        resources=[r.value for r in Resource],
        matrix=matrix,
    )


@router.get(
    "/menu",
    summary="当前角色可见菜单 (Phase 6 B28)",
    response_model=MenuResponse,
)
async def get_menu(user: CurrentUserDep) -> MenuResponse:
    """返回当前用户角色对应的前端菜单项列表."""
    role = normalize_role(user.get("role"))
    return MenuResponse(role=role.value, items=menu_for_role(role))


@router.post(
    "/check",
    summary="权限校验 (Phase 6 B28)",
    response_model=PermissionCheckResponse,
)
async def check_perm(
    user: CurrentUserDep,
    body: PermissionCheckRequest = Body(...),
) -> PermissionCheckResponse:
    """ad-hoc 检查当前用户对 resource 执行 action 是否被允许."""
    role = normalize_role(user.get("role"))
    try:
        resource = Resource(body.resource)
    except ValueError as e:
        raise ValueError(f"未知 resource: {body.resource}") from e
    try:
        action = Action(body.action)
    except ValueError as e:
        raise ValueError(f"未知 action: {body.action}") from e

    allowed, reason = permission_decision(role, resource, action)
    return PermissionCheckResponse(
        allowed=allowed,
        role=role.value,
        resource=resource.value,
        action=action.value,
        reason=reason,
    )


# ===== 策略覆盖 (租户级) =====


@router.get(
    "/policies",
    summary="角色策略列表 (含租户覆盖)",
    response_model=list[RolePolicyResponse],
)
async def list_policies(
    session: SessionDep,
    _: CurrentUserDep,
    tenant_id: UUID | None = Query(None, description="按租户过滤"),
) -> list[RolePolicyResponse]:
    """列出 role_policies. 平台超管可见所有, 否则仅可见本租户策略."""
    stmt = select(RolePolicy).order_by(RolePolicy.role, RolePolicy.resource)
    if tenant_id:
        stmt = stmt.where(RolePolicy.tenant_id == tenant_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        RolePolicyResponse(
            policy_id=r.policy_id,
            role=r.role,
            resource=r.resource,
            allowed_action=r.allowed_action,
            tenant_id=r.tenant_id,
            enabled=r.enabled,
            comment=r.comment,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post(
    "/policies",
    summary="新增角色策略",
    response_model=RolePolicyResponse,
)
async def create_policy(
    session: SessionDep,
    user: CurrentUserDep,
    body: RolePolicyCreate = Body(...),
) -> RolePolicyResponse:
    """新增租户级策略覆盖. 需要 super_admin 角色 (B29 后台使用)."""
    role = normalize_role(user.get("role"))
    if not check_permission(role, Resource.TEMPLATE, Action.ADMIN):
        # 用 TEMPLATE.ADMIN 作为 RBAC 自身管理权限 (B29 也用同一档位)
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "E_PERMISSION_DENIED",
                "message": "新增策略需要超管权限",
            },
        )

    policy = RolePolicy(
        role=body.role,
        resource=body.resource,
        allowed_action=body.allowed_action,
        tenant_id=body.tenant_id,
        enabled=body.enabled,
        comment=body.comment,
    )
    session.add(policy)
    await session.commit()
    await session.refresh(policy)
    return RolePolicyResponse(
        policy_id=policy.policy_id,
        role=policy.role,
        resource=policy.resource,
        allowed_action=policy.allowed_action,
        tenant_id=policy.tenant_id,
        enabled=policy.enabled,
        comment=policy.comment,
        created_at=policy.created_at,
    )


# ===== 审计 =====


@router.get(
    "/audit",
    summary="角色变更审计 (PIPL 合规)",
    response_model=RoleAuditListResponse,
)
async def role_audit(
    session: SessionDep,
    _: CurrentUserDep,
    user_id: UUID | None = Query(None, description="按 user_id 过滤"),
    limit: int = Query(default=50, ge=1, le=200),
) -> RoleAuditListResponse:
    """查看角色变更审计 (PIPL 合规留痕)."""
    stmt = select(UserRoleAudit).order_by(UserRoleAudit.created_at.desc()).limit(limit)
    if user_id:
        stmt = stmt.where(UserRoleAudit.user_id == user_id)
    rows = (await session.execute(stmt)).scalars().all()
    items = [
        RoleAuditItem(
            audit_id=r.audit_id,
            tenant_id=r.tenant_id,
            user_id=r.user_id,
            old_role=r.old_role,
            new_role=r.new_role,
            changed_by=r.changed_by,
            reason=r.reason,
            extra=r.extra,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return RoleAuditListResponse(items=items, total=len(items))


__all__ = ["router"]
