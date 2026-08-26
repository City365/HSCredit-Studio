"""认证 API 路由 — 登录 / 刷新 / 登出.

设计要点：

- ``POST /api/v1/auth/login``：邮箱 + 密码 + tenant_slug，返回 token pair。
- ``POST /api/v1/auth/refresh``：用 refresh token 换新 token 对。
- ``POST /api/v1/auth/logout``：Phase 1 无状态，前端丢弃 token；
  仍接受 ``LogoutRequest`` 以保持 OpenAPI 契约稳定。
- 这三个路由均为**公开路由**（无需 tenant slug），在
  ``TenantMiddleware._PUBLIC_PATHS`` 中已排除。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.database import get_session
from hscredit_studio.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    RefreshResponse,
)
from hscredit_studio.services.auth import authenticate, logout, refresh_tokens

router = APIRouter(tags=["认证"])


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="登录",
    description="邮箱 + 密码 + tenant_slug 登录，返回 access/refresh token pair",
)
async def login(
    req: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> LoginResponse:
    """邮箱 + 密码 + tenant_slug 登录."""
    return await authenticate(session, req)


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="刷新令牌",
    description="用 refresh token 换新的 access/refresh token pair",
)
async def refresh(
    req: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> RefreshResponse:
    """用 refresh token 换新的 token 对."""
    tokens = await refresh_tokens(session, req.refresh_token)
    return RefreshResponse(tokens=tokens)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="登出",
    description="登出（Phase 1 无状态；Phase 2 引入 token blacklist）",
)
async def logout_endpoint(
    req: LogoutRequest,
    session: AsyncSession = Depends(get_session),
) -> None:
    """登出（Phase 1 无状态实现，Phase 2 引入 Redis token blacklist）.

    当前实现：客户端丢弃 token 即可完成登出，服务端不写 DB、
    不校验 ``refresh_token`` 是否仍有效（避免泄露 token 活性）。
    仅记录审计入参，待 Phase 2 引入 Redis 后启用 ``services.auth.logout``。
    """
    # 简化：Phase 1 仅客户端丢弃 token。
    # 预留审计入参避免静默丢弃（FutureWarning suppressed）
    _ = req