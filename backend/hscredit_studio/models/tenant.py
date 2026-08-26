"""租户与多租户成员模型.

按 09 第 9.3.1 节实现，覆盖：

- :class:`Tenant` — 租户主表（plan / status / settings）
- :class:`TenantMember` — 租户成员关联（含角色）
- :class:`UserInvitation` — 邀请记录
- :class:`ApiKey` — API 密钥（仅存 key 哈希，不存明文）
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hscredit_studio.core.database import Base
from hscredit_studio.models.base import (
    ModelSerializerMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)


# ===== Enum 值常量（用于 alembic 与 ORM 共享） =====

PLAN_VALUES = ("free", "pro", "enterprise")
"""Tenant.plan 枚举值."""

TENANT_STATUS_VALUES = ("active", "suspended", "archived")
"""Tenant.status 枚举值.

注：09 文档使用 ``deleted``，此处统一为 ``archived`` 以与平台其它
"归档" 概念保持一致；详细见 migration ``plan``/``status`` 部分注释。
"""

MEMBER_ROLE_VALUES = ("owner", "admin", "analyst", "viewer")
"""TenantMember.role 枚举值（owner/admin/analyst/viewer）."""

MEMBER_STATUS_VALUES = ("active", "pending", "removed")
"""TenantMember.status 枚举值."""


class Tenant(Base, TimestampMixin, SoftDeleteMixin, ModelSerializerMixin):
    """租户表.

    全平台最高层级隔离单元；所有业务数据通过 ``tenant_id`` 外键关联到此表。

    唯一约束：

    - ``slug`` 全局唯一（URL 友好短名）。
    """

    __tablename__ = "tenants"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="租户显示名")
    slug: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="URL slug，唯一短名（[a-z0-9-]）",
    )
    plan: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'free'"),
        comment=f"订阅计划，取值 {PLAN_VALUES}",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'active'"),
        comment=f"租户状态，取值 {TENANT_STATUS_VALUES}",
    )
    settings: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="租户级配置（默认参数、阈值等）",
    )

    # 关系
    members: Mapped[list["TenantMember"]] = relationship(
        "TenantMember",
        back_populates="tenant",
        cascade="save-update",
    )
    invitations: Mapped[list["UserInvitation"]] = relationship(
        "UserInvitation",
        back_populates="tenant",
        cascade="save-update",
    )

    __table_args__ = (
        Index("ix_tenants_status", "status"),
    )


class TenantMember(Base, TimestampMixin, ModelSerializerMixin):
    """租户成员关联（含角色）.

    复合 PK ``(tenant_id, user_id)``；一个用户可在多个租户拥有不同角色。
    """

    __tablename__ = "tenant_members"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment=f"成员角色，取值 {MEMBER_ROLE_VALUES}",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'active'"),
        comment=f"成员状态，取值 {MEMBER_STATUS_VALUES}",
    )
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        comment="发起邀请的用户 ID",
    )
    joined_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=text("now()"),
        comment="加入时间",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=text("now()"),
    )

    # 关系
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="members")

    __table_args__ = (
        # 通过列定义已声明 PK；此处仅声明按需索引
        Index("ix_tenant_members_user", "user_id"),
    )


class UserInvitation(Base, TimestampMixin, ModelSerializerMixin):
    """用户邀请记录.

    一次性邀请 token 通过 ``token`` 字段标识（无需存哈希，因为接受时
    即失效并被消费，可视为一次性凭据）。
    """

    __tablename__ = "user_invitations"

    invitation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False, comment="被邀请邮箱")
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment=f"邀请授予角色，取值 {MEMBER_ROLE_VALUES}",
    )
    token: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        comment="一次性邀请 token（接受后置空）",
    )
    expires_at: Mapped[datetime] = mapped_column(nullable=False, comment="邀请过期时间")
    accepted_at: Mapped[datetime | None] = mapped_column(nullable=True, comment="接受时间")
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    # 关系
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="invitations")


class ApiKey(Base, TimestampMixin, SoftDeleteMixin, TenantMixin, ModelSerializerMixin):
    """API 密钥元数据.

    仅存 ``key_hash``（bcrypt），绝不存明文；``key_prefix`` 用于 UI
    显示（前 8 位）；``scopes`` 是字符串列表（JSONB 数组）。
    """

    __tablename__ = "api_keys"

    api_key_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="密钥名称（如 CI 机器人）")
    key_prefix: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="可显示前缀（前 8 位）",
    )
    key_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        comment="bcrypt 哈希值",
    )
    scopes: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        comment="作用域字符串数组（['read:runs', 'write:workflows', ...]）",
    )
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)


__all__ = [
    "PLAN_VALUES",
    "TENANT_STATUS_VALUES",
    "MEMBER_ROLE_VALUES",
    "MEMBER_STATUS_VALUES",
    "Tenant",
    "TenantMember",
    "UserInvitation",
    "ApiKey",
]
