"""FastAPI 依赖注入."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.database import get_session
from hscredit_studio.core.security import decode_token
from hscredit_studio.services.rbac import (
    Action,
    Resource,
    Role,
    check_permission,
    normalize_role,
    permission_decision,
)


async def get_current_user(
    authorization: str | None = Header(default=None),
) -> dict:
    """从 Authorization 头获取当前用户."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "E_AUTH_REQUIRED", "message": "未提供访问令牌"},
        )

    token = authorization.removeprefix("Bearer ")
    try:
        payload = decode_token(token)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "E_AUTH_REQUIRED", "message": "无效的访问令牌"},
        ) from err

    return payload


async def get_tenant(
    tenant_slug: Annotated[str, Path(...)],
    user: Annotated[dict, Depends(get_current_user)],
) -> str:
    """获取并校验当前租户（URL tenant_slug 必须与 JWT tenant_slug 一致）."""
    user_tenant = user.get("tenant_slug")
    if user_tenant != tenant_slug:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "E_TENANT_FORBIDDEN", "message": "无权访问该租户"},
        )
    return user["tenant_id"]


def current_role(user: Annotated[dict, Depends(get_current_user)]) -> Role:
    """提取并规范化当前用户角色 (Phase 6 B28).

    JWT payload 优先取 ``role`` 字段 (新签发 token), 缺失则视为 NONE.
    """
    return normalize_role(user.get("role"))


# ===== Phase 6 B28 RBAC 依赖 =====


def require_permission(resource: Resource, action: Action):
    """依赖工厂: 检查当前用户对 ``resource`` 执行 ``action`` 的权限 (Phase 6 B28 验收).

    用法::

        @router.post("/workflows", dependencies=[Depends(require_permission(Resource.WORKFLOW, Action.WRITE))])
        async def create_workflow(...): ...

    失败返回 403, ``detail.code = E_PERMISSION_DENIED``.
    """
    return _RequirePermission(resource, action)


class _RequirePermission:
    """依赖对象 — 可序列化 + FastAPI 缓存 key 友好."""

    def __init__(self, resource: Resource, action: Action) -> None:
        self.resource = resource
        self.action = action

    async def __call__(
        self,
        user: Annotated[dict, Depends(get_current_user)],
    ) -> dict:
        role = normalize_role(user.get("role"))
        allowed, reason = permission_decision(role, self.resource, self.action)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "E_PERMISSION_DENIED",
                    "message": "权限不足",
                    "resource": self.resource.value,
                    "action": self.action.value,
                    "role": role.value,
                    "reason": reason,
                },
            )
        return user

    def __repr__(self) -> str:  # pragma: no cover - debug
        return f"require_permission({self.resource.value}, {self.action.value})"


def require_role(required: Role):
    """依赖工厂: 要求最低角色等级 (Phase 6 B28).

    用法::

        @router.get("/admin/...", dependencies=[Depends(require_role(Role.SUPER_ADMIN))])
        async def admin_endpoint(...): ...
    """
    return _RequireRole(required)


class _RequireRole:
    def __init__(self, required: Role) -> None:
        self.required = required

    async def __call__(
        self,
        user: Annotated[dict, Depends(get_current_user)],
    ) -> dict:
        role = normalize_role(user.get("role"))
        if role.rank < self.required.rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "E_PERMISSION_DENIED",
                    "message": f"需要角色 {self.required.value}",
                    "required_role": self.required.value,
                    "actual_role": role.value,
                },
            )
        return user

    def __repr__(self) -> str:  # pragma: no cover - debug
        return f"require_role({self.required.value})"


# 类型别名
SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUserDep = Annotated[dict, Depends(get_current_user)]
TenantDep = Annotated[str, Depends(get_tenant)]


# 便捷: ``check_permission`` 重新导出 (供路由层 ad-hoc 使用)
__all__ = [
    "CurrentUserDep",
    "SessionDep",
    "TenantDep",
    "check_permission",
    "current_role",
    "require_permission",
    "require_role",
]
