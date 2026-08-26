"""用户模型.

按 09 第 9.3.1 节 ``users`` 表实现：

- 全平台唯一用户（多租户共享）
- ``password_hash`` 字段在 SSO 模式下可为空
- ``status`` 取值 ``active`` / ``locked`` / ``disabled``
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from hscredit_studio.core.database import Base
from hscredit_studio.models.base import (
    ModelSerializerMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


USER_STATUS_VALUES = ("active", "locked", "disabled")
"""User.status 枚举值."""


class User(Base, TimestampMixin, SoftDeleteMixin, ModelSerializerMixin):
    """平台全局用户表.

    一行代表一个登录身份；可属于多个 tenant（通过 ``tenant_members`` 关联）。
    """

    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(
        String(254),
        nullable=False,
        unique=True,
        comment="登录邮箱（唯一）",
    )
    display_name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="显示名（可空，首次登录回填）",
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="bcrypt 密码哈希；SSO 模式下为空",
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'active'"),
        comment=f"账号状态，取值 {USER_STATUS_VALUES}",
    )
    locale: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        server_default=text("'zh-CN'"),
        comment="用户偏好语言（如 zh-CN / en-US）",
    )


__all__ = ["USER_STATUS_VALUES", "User"]
