"""通知配置与发送记录模型 — Phase 5 B23.

依据 docs/ROADMAP.md Phase 5 B23:

> 通知发送记录 (Slack / 企微 / SMTP)
> 通知模板: 账单 / 额度预警 / 告警

表设计:

- ``notification_configs`` — 租户级通知配置 (哪些 channel 接收哪些 template)
- ``notification_logs`` — 发送历史 (成功/失败/dry_run)
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from hscredit_studio.core.database import Base
from hscredit_studio.models.base import (
    TenantMixin,
    TimestampMixin,
)

NOTIFICATION_CHANNEL_VALUES = ("slack", "wecom", "email")
NOTIFICATION_STATUS_VALUES = ("pending", "sent", "failed", "dry_run")


class NotificationConfig(Base, TimestampMixin, TenantMixin):
    """通知配置 — Phase 5 B23.

    记录租户启用了哪些 channel (含 webhook URL / SMTP 配置等敏感字段,
    生产环境应加密存储, 当前迭代明文仅用于本地 dev).
    """

    __tablename__ = "notification_configs"

    config_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    channel: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment=f"通道 {NOTIFICATION_CHANNEL_VALUES}",
    )
    template_key: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="仅接收该模板 (None = 全模板)",
    )
    recipient: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="收件人 (email 地址 / webhook URL override)",
    )
    config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="扩展配置 (邮件端口/SMTP 用户等)",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        comment="是否启用",
    )

    __table_args__ = (
        Index("ix_notification_configs_tenant", "tenant_id"),
        Index("ix_notification_configs_channel", "channel"),
    )


class NotificationLog(Base, TimestampMixin, TenantMixin):
    """通知发送历史 — Phase 5 B23."""

    __tablename__ = "notification_logs"

    log_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    template_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="模板键",
    )
    channel: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment=f"通道 {NOTIFICATION_CHANNEL_VALUES}",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'pending'"),
        comment=f"状态 {NOTIFICATION_STATUS_VALUES}",
    )
    title: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        comment="通知标题",
    )
    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="通知正文",
    )
    recipient: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="收件人",
    )
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="失败错误信息",
    )

    __table_args__ = (
        Index("ix_notification_logs_tenant_created", "tenant_id", "created_at"),
        Index("ix_notification_logs_status", "status"),
        Index("ix_notification_logs_template", "template_key"),
    )


__all__ = [
    "NOTIFICATION_CHANNEL_VALUES",
    "NOTIFICATION_STATUS_VALUES",
    "NotificationConfig",
    "NotificationLog",
]
