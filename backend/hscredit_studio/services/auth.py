"""认证服务 — 登录、刷新、登出.

设计要点（见 ``docs/design/14-api-specification.md`` 14.5.2）：

- **登录**：

  1. 按 ``tenant_slug`` 查租户，不存在 → ``AuthenticationError``。
  2. 按 ``email`` 查用户（全平台唯一），未找到或密码错误 → ``AuthenticationError``
     （不区分错误原因，防枚举）。
  3. 校验 ``tenant_members`` 关系是否为 ``active``，否则 → ``TenantForbiddenError``。
  4. 更新 ``last_login_at``，提交事务。
  5. 颁发 access + refresh token pair。

- **刷新**：解码 refresh token → 校验 ``type == 'refresh'`` →
  校验用户 / 租户 / 成员关系仍有效 → 颁发新 token pair。
  （当前不实现 refresh token 黑名单 / 旋转，待 Redis 接入后补齐。）

- **登出**：Phase 1 无状态 JWT，前端丢弃即可；
  Phase 2 引入 Redis token blacklist / 撤销 family。
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.config import settings
from hscredit_studio.core.exceptions import AuthenticationError, TenantForbiddenError
from hscredit_studio.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from hscredit_studio.models import Tenant, TenantMember, User
from hscredit_studio.services import audit as audit_service
from hscredit_studio.schemas.auth import (
    LoginRequest,
    LoginResponse,
    TokenPair,
    UserInfo,
)


def _build_token_pair(user: User, tenant: Tenant, role: str) -> TokenPair:
    """构造 access + refresh token 对.

    Token claims:

    - ``sub`` — 用户 UUID（字符串）
    - ``type`` — ``"access"`` / ``"refresh"``
    - ``tenant_id`` — 租户 UUID
    - ``tenant_slug`` — 租户 slug
    - ``role`` — 在该租户的角色
    - ``exp`` / ``iat`` — 由 ``create_*_token`` 自动填充
    """
    extra_claims: dict[str, str] = {
        "tenant_id": str(tenant.tenant_id),
        "tenant_slug": tenant.slug,
        "role": role,
    }
    access_token = create_access_token(
        subject=str(user.user_id),
        extra_claims=extra_claims,
    )
    refresh_token = create_refresh_token(
        subject=str(user.user_id),
        extra_claims=extra_claims,
    )
    expires_in = settings.jwt_access_token_expire_minutes * 60
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
    )


async def authenticate(session: AsyncSession, req: LoginRequest) -> LoginResponse:
    """邮箱 + 密码 + tenant_slug 登录，返回 token pair + 用户上下文.

    Raises
    ------
    AuthenticationError
        租户不存在 / 用户不存在 / 密码错误。
    TenantForbiddenError
        用户不属于该租户或成员关系非 active。
    """
    # 1. 查租户
    tenant = await session.scalar(
        select(Tenant).where(Tenant.slug == req.tenant_slug, Tenant.deleted_at.is_(None))
    )
    if tenant is None:
        # 审计: 失败登录 (租户不存在)
        await audit_service.record_login(
            session,
            tenant_id=UUID(int=0),  # 占位,租户不存在
            user_id=None,
            success=False,
            email=req.email,
        )
        await session.commit()
        raise AuthenticationError(f"租户 {req.tenant_slug} 不存在")

    # 2. 查用户（全平台唯一）
    user = await session.scalar(
        select(User).where(User.email == req.email, User.deleted_at.is_(None))
    )
    if user is None or not verify_password(req.password, user.password_hash or ""):
        # 不区分用户不存在 / 密码错误，防止枚举
        await audit_service.record_login(
            session,
            tenant_id=tenant.tenant_id,
            user_id=None,
            success=False,
            email=req.email,
        )
        await session.commit()
        raise AuthenticationError("邮箱或密码错误")

    # 3. 校验用户在该租户的成员关系
    member = await session.scalar(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant.tenant_id,
            TenantMember.user_id == user.user_id,
            TenantMember.status == "active",
        )
    )
    if member is None:
        await audit_service.record_login(
            session,
            tenant_id=tenant.tenant_id,
            user_id=user.user_id,
            success=False,
            email=req.email,
        )
        await session.commit()
        raise TenantForbiddenError(f"用户 {req.email} 不属于租户 {req.tenant_slug}")

    # 4. 更新最后登录时间
    user.last_login_at = datetime.utcnow()  # naive UTC — 匹配 DB TIMESTAMP 列
    await session.commit()

    # 5. 构造 token
    tokens = _build_token_pair(user, tenant, member.role)

    # 6. 审计: 登录成功
    await audit_service.record_login(
        session,
        tenant_id=tenant.tenant_id,
        user_id=user.user_id,
        success=True,
        email=req.email,
    )
    await session.commit()

    # display_name 在 schema 中是必填 str，但 User.display_name 可空，
    # 这里回退到 email 本地部分（如 ``zhangsan@example.com`` → ``zhangsan``）。
    display_name = user.display_name or user.email.split("@", 1)[0]

    return LoginResponse(
        tokens=tokens,
        user=UserInfo(
            user_id=user.user_id,
            email=user.email,
            display_name=display_name,
            status=user.status,
            locale=user.locale or "zh-CN",
            email_verified_at=user.email_verified_at,
            last_login_at=user.last_login_at,
        ),
        tenant_slug=tenant.slug,
        role=member.role,
    )


async def refresh_tokens(session: AsyncSession, refresh_token: str) -> TokenPair:
    """用 refresh token 换新的 token 对.

    Raises
    ------
    AuthenticationError
        token 无效 / 类型错误 / 用户失效 / 租户失效。
    TenantForbiddenError
        成员关系已失效。
    """
    try:
        payload = decode_token(refresh_token)
    except (ValueError, JWTError) as e:
        raise AuthenticationError(f"Refresh token 无效: {e}") from e

    if payload.get("type") != "refresh":
        raise AuthenticationError("需要 refresh token")

    user_id = UUID(payload["sub"])
    tenant_id = UUID(payload["tenant_id"])
    role = payload.get("role", "viewer")

    # 校验用户仍存在且有效
    user = await session.get(User, user_id)
    if user is None or user.deleted_at is not None or user.status != "active":
        raise AuthenticationError("用户不存在或已禁用")

    # 校验租户仍存在
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None or tenant.deleted_at is not None:
        raise AuthenticationError("租户不存在或已归档")

    # 校验成员关系仍有效
    member = await session.scalar(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.user_id == user_id,
            TenantMember.status == "active",
        )
    )
    if member is None:
        raise TenantForbiddenError("成员关系已失效")

    return _build_token_pair(user, tenant, role)


async def logout(
    session: AsyncSession,
    refresh_token: str,
    user_id: UUID,
) -> None:
    """登出 — Phase 1 仅做无状态 JWT 失效（由前端丢弃 token）.

    Phase 2 引入 Redis token blacklist 后，将在此函数中：

    - 将 ``refresh_token`` 的 jti 写入 Redis 黑名单（TTL = 剩余有效期）；
    - 可选：将同一 token family 全部加入黑名单（refresh token rotation 安全）。

    当前实现：仅记录入参（用于审计埋点），不写 DB、不抛异常。
    """
    # 审计埋点预留：当前不写 DB，避免无意义写入。
    # TODO(phase-2): Redis token blacklist + audit event。
    _ = (session, refresh_token, user_id)


__all__ = ["authenticate", "refresh_tokens", "logout"]