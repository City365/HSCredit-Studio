"""认证相关 schema.

登录、JWT 令牌、用户信息等入参 / 出参。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from hscredit_studio.schemas.common import BaseSchema


class LoginRequest(BaseModel):
    """登录请求体.

    Attributes
    ----------
    email:
        登录邮箱。
    password:
        密码（明文；HTTPS 传输，service 层立即 bcrypt 校验）。
    tenant_slug:
        租户短名（URL slug），正则 ``^[a-z0-9-]+$``。
    """

    # 注：BaseModel（不带 from_attributes）即可，避免 ORM 误用
    email: EmailStr = Field(..., description="登录邮箱")
    password: str = Field(..., min_length=8, max_length=128, description="密码（明文）")
    tenant_slug: str = Field(
        ...,
        min_length=2,
        max_length=64,
        pattern=r"^[a-z0-9-]+$",
        description="租户短名（URL slug）",
    )


class TokenPair(BaseModel):
    """JWT 双令牌对.

    Attributes
    ----------
    access_token:
        短寿命 access token（默认 30 分钟）。
    refresh_token:
        长寿命 refresh token（默认 7 天），用于刷新 access_token。
    token_type:
        固定 ``"bearer"``，符合 OAuth2 / RFC 6750。
    expires_in:
        access_token 剩余有效秒数（前端可在倒计时归零前主动刷新）。
    """

    access_token: str = Field(..., description="访问令牌")
    refresh_token: str = Field(..., description="刷新令牌")
    token_type: str = Field(default="bearer", description="令牌类型（固定 bearer）")
    expires_in: int = Field(..., ge=0, description="access_token 过期秒数")


class UserInfo(BaseSchema):
    """当前用户上下文.

    Attributes
    ----------
    user_id:
        用户 UUID。
    email:
        登录邮箱。
    display_name:
        显示名（未设置时回退 email 本地部分）。
    status:
        用户状态，取值 ``active`` / ``locked`` / ``disabled``。
    locale:
        用户偏好语言（默认 ``zh-CN``）。
    email_verified_at:
        邮箱验证时间（NULL 表示未验证）。
    last_login_at:
        上次登录时间（NULL 表示从未登录）。
    """

    user_id: UUID = Field(..., description="用户 UUID")
    email: EmailStr = Field(..., description="登录邮箱")
    display_name: str = Field(..., description="显示名")
    status: str = Field(..., description="账号状态")
    locale: str = Field(default="zh-CN", description="偏好语言")
    email_verified_at: datetime | None = Field(default=None, description="邮箱验证时间")
    last_login_at: datetime | None = Field(default=None, description="上次登录时间")


class LoginResponse(BaseModel):
    """登录成功响应.

    Attributes
    ----------
    tokens:
        JWT 令牌对。
    user:
        用户信息。
    tenant_slug:
        登录的租户 slug。
    role:
        用户在该租户的角色（如 ``owner`` / ``admin`` / ``analyst`` / ``viewer``）。
    """

    tokens: TokenPair = Field(..., description="JWT 令牌对")
    user: UserInfo = Field(..., description="用户信息")
    tenant_slug: str = Field(..., description="租户 slug")
    role: str = Field(..., description="用户在当前租户的角色")


class RefreshRequest(BaseModel):
    """刷新令牌请求体.

    Attributes
    ----------
    refresh_token:
        上次登录获得的 refresh token。
    """

    refresh_token: str = Field(..., min_length=1, description="刷新令牌")


class RefreshResponse(BaseModel):
    """刷新令牌成功响应.

    Attributes
    ----------
    tokens:
        新的 JWT 令牌对。
    """

    tokens: TokenPair = Field(..., description="新的 JWT 令牌对")


class LogoutRequest(BaseModel):
    """登出请求体.

    Attributes
    ----------
    refresh_token:
        待撤销的 refresh token（服务端加入黑名单或删除会话）。
    """

    refresh_token: str = Field(..., min_length=1, description="待撤销的刷新令牌")


__all__ = [
    "LoginRequest",
    "TokenPair",
    "UserInfo",
    "LoginResponse",
    "RefreshRequest",
    "RefreshResponse",
    "LogoutRequest",
]