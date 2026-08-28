"""Webhook 模型 — Phase 8 B35.

设计:

- :class:`WebhookSubscription` — 租户的 webhook 订阅
- :class:`WebhookDelivery` — 单次投递尝试记录

事件类型由 :class:`hscredit_studio.services.webhooks.WebhookEvent` 枚举定义.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hscredit_studio.core.database import Base
from hscredit_studio.models.base import TimestampMixin


class WebhookSubscription(Base, TimestampMixin):
    """Webhook 订阅 (Phase 8 B35).

    租户订阅平台事件 → 平台向 url POST 事件数据 (HMAC 签名).

    Attributes:
        subscription_id: 主键 UUID.
        tenant_id: 租户.
        url: 目标 URL (POST 接收).
        secret: HMAC 签名密钥 (32 字节 hex).
        events: 监听事件列表 (空 = 全部).
        active: 是否启用.
        description: 描述.
    """

    __tablename__ = "webhook_subscriptions"

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="目标 URL (POST 接收事件)",
    )
    secret: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="HMAC-SHA256 签名密钥 (hex)",
    )
    events: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(64)),
        nullable=True,
        default=list,
        comment="监听事件列表 (空 = 全部)",
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        comment="是否启用",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
        comment="订阅描述",
    )

    deliveries: Mapped[list[WebhookDelivery]] = relationship(
        "WebhookDelivery",
        back_populates="subscription",
        cascade="all, delete-orphan",
    )


class WebhookDelivery(Base, TimestampMixin):
    """Webhook 单次投递记录 (Phase 8 B35)."""

    __tablename__ = "webhook_deliveries"

    delivery_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("webhook_subscriptions.subscription_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="事件类型",
    )
    payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="事件 payload (JSON)",
    )
    body: Mapped[bytes | None] = mapped_column(
        Text,  # PostgreSQL BYTEA 但 SQLAlchemy Text 也接受 bytes
        nullable=True,
        comment="完整 HTTP body (已签名)",
    )
    attempt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="已尝试次数",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
        index=True,
        comment="状态 (pending/success/failed/retrying/cancelled)",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="最后错误信息",
    )
    response_status: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="目标 HTTP 响应码",
    )
    response_body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="目标响应 body (前 500 字符)",
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("NOW()"),
        comment="计划投递时间 (用于重试调度)",
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="实际投递成功时间",
    )

    subscription: Mapped[WebhookSubscription] = relationship(
        "WebhookSubscription",
        back_populates="deliveries",
    )


# 复合索引: (status, scheduled_at) 用于后台重试扫描
Index(
    "ix_webhook_deliveries_status_scheduled",
    WebhookDelivery.status,
    WebhookDelivery.scheduled_at,
)


__all__ = ["WebhookDelivery", "WebhookSubscription"]
