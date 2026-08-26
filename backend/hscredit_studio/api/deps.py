"""FastAPI 依赖注入."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.database import get_session
from hscredit_studio.core.security import decode_token


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
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "E_AUTH_REQUIRED", "message": "无效的访问令牌"},
        )

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


# 类型别名
SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUserDep = Annotated[dict, Depends(get_current_user)]
TenantDep = Annotated[str, Depends(get_tenant)]
