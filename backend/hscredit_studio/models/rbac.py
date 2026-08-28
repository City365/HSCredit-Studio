"""RBAC 模型 — Phase 6 B28.

依据 docs/ROADMAP.md Phase 6 B28:

- 角色矩阵在代码层由 :mod:`hscredit_studio.services.rbac` 定义.
- :class:`RolePolicy` 提供**租户级**权限覆盖 (例如某租户给 analyst 临时开 billing.write).
- :class:`UserRoleAudit` 记录角色变更, 用于 PIPL + 内部审计追溯.
- :attr:`User.is_super_admin` 是平台超管标记 (B29 跨租户后台使用).
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from hscredit_studio.core.database import Base
from hscredit_studio.models.base import TimestampMixin


class RolePolicy(Base, TimestampMixin):
    """角色 × 资源策略表 (Phase 6 B28).

    - ``role`` / ``resource`` / ``tenant_id`` 唯一 (NULL tenant_id = 全局覆盖).
    - ``enabled=False`` 用于软删除策略.
    """

    __tablename__ = "role_policies"

    policy_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    resource: Mapped[str] = mapped_column(String(32), nullable=False)
    allowed_action: Mapped[str] = mapped_column(String(16), nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="NULL=全局覆盖, 否则=租户级覆盖",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    comment: Mapped[str | None] = mapped_column(String(256), nullable=True)

    __table_args__ = (
        Index(
            "uq_role_policies_role_resource_tenant",
            "role",
            "resource",
            "tenant_id",
            unique=True,
        ),
    )


class UserRoleAudit(Base, TimestampMixin):
    """用户角色变更审计 (Phase 6 B28).

    每次 :class:`TenantMember.role` 变更或 super_admin 标记变化均落一行.
    """

    __tablename__ = "user_role_audit"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    old_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_role: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    extra: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    __table_args__ = (
        Index("ix_user_role_audit_user", "user_id"),
        Index("ix_user_role_audit_tenant", "tenant_id"),
        Index("ix_user_role_audit_created", "created_at"),
    )


__all__ = ["RolePolicy", "UserRoleAudit"]
