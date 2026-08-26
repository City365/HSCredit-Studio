"""审计事件模型.

按 09 第 9.3.10 节 ``audit_events`` 表实现：

- 最小骨架（Phase 1 不含完整事件分类，Phase 4 扩展）
- 索引 ``(tenant_id, occurred_at DESC)`` 和 ``(user_id, occurred_at DESC)``
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from hscredit_studio.core.database import Base
from hscredit_studio.models.base import (
    ModelSerializerMixin,
    TenantMixin,
)


class AuditEvent(Base, ModelSerializerMixin):
    """审计事件（append-only）.

    PK 用 ``event_id`` UUID（应用层 ``uuid.uuid4``）而非 BIGSERIAL，
    便于跨数据库合并与全局搜索。生产环境如需高频写入可改为 BIGSERIAL。
    """

    __tablename__ = "audit_events"

    event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        comment="发起者（系统事件可空）",
    )
    action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="动作（login/logout/create_workflow/submit_run/...）",
    )
    resource_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="资源类型（workflow/run/node/template/user）",
    )
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="资源 ID",
    )
    details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="附加上下文",
    )
    ip_address: Mapped[str | None] = mapped_column(
        INET,
        nullable=True,
        comment="来源 IP",
    )
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True, comment="浏览器 UA")
    occurred_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_audit_events_tenant_occurred", "tenant_id", "occurred_at"),
        Index("ix_audit_events_user_occurred", "user_id", "occurred_at"),
        Index("ix_audit_events_action", "tenant_id", "action", "occurred_at"),
    )


__all__ = ["AuditEvent"]
