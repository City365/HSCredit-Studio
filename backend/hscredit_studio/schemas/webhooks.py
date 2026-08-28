"""Webhook Schemas — Phase 8 B35."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from hscredit_studio.services.webhooks import WebhookDeliveryStatus, WebhookEvent


class WebhookSubscriptionCreate(BaseModel):
    """创建 Webhook 订阅请求 (B35 验收)."""

    url: str = Field(..., min_length=8, max_length=2048, description="目标 URL")
    events: list[WebhookEvent] = Field(
        default_factory=list,
        description="监听事件列表 (空 = 全部)",
    )
    active: bool = Field(default=True, description="是否启用")
    description: str = Field(default="", max_length=512)


class WebhookSubscriptionUpdate(BaseModel):
    """更新 Webhook 订阅."""

    url: str | None = Field(default=None, min_length=8, max_length=2048)
    events: list[WebhookEvent] | None = None
    active: bool | None = None
    description: str | None = Field(default=None, max_length=512)


class WebhookSubscriptionResponse(BaseModel):
    """Webhook 订阅响应 (含 secret 明文, 仅创建时返回一次)."""

    subscription_id: str
    tenant_id: str
    url: str
    events: list[str]
    active: bool
    description: str
    created_at: datetime
    secret: str | None = Field(default=None, description="仅创建/重置密钥时返回")


class WebhookSubscriptionListResponse(BaseModel):
    """Webhook 订阅列表."""

    items: list[WebhookSubscriptionResponse]
    total: int


class WebhookDeliveryItem(BaseModel):
    """Webhook 投递记录项."""

    delivery_id: str
    subscription_id: str
    event: str
    status: WebhookDeliveryStatus
    attempt: int
    response_status: int | None
    last_error: str | None
    scheduled_at: datetime
    delivered_at: datetime | None
    created_at: datetime


class WebhookDeliveryListResponse(BaseModel):
    """Webhook 投递记录列表."""

    items: list[WebhookDeliveryItem]
    total: int


class WebhookTestRequest(BaseModel):
    """Webhook 测试发送请求."""

    url: str = Field(..., min_length=8, max_length=2048)
    secret: str | None = Field(default=None, description="留空则自动生成")
    event: str = Field(default="webhook.test", max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class WebhookTestResponse(BaseModel):
    """Webhook 测试发送响应."""

    success: bool
    response_status: int | None
    error: str | None
    secret_used: str
    delivery_id: str


class WebhookEventPublishRequest(BaseModel):
    """事件发布请求 (内部 API, 用于其他模块触发事件)."""

    event: WebhookEvent
    payload: dict[str, Any] = Field(default_factory=dict)


class WebhookEventPublishResponse(BaseModel):
    """事件发布响应."""

    event_id: str
    event: WebhookEvent
    tenant_id: str
    enqueued_count: int
    published_at: datetime


class WebhookSignatureVerifyRequest(BaseModel):
    """Webhook 签名验证请求 (供租户端调试)."""

    secret: str = Field(..., min_length=8, max_length=128)
    payload: str = Field(..., description="原始 body (字符串)")
    signature: str = Field(..., description="X-HSCredit-Signature 值")
    timestamp: int = Field(..., description="X-HSCredit-Timestamp 值")


class WebhookSignatureVerifyResponse(BaseModel):
    """Webhook 签名验证响应."""

    valid: bool
    reason: str | None = None


class WebhookEventsResponse(BaseModel):
    """支持的事件类型列表."""

    events: list[dict[str, str]]
    total: int


__all__ = [
    "WebhookDeliveryItem",
    "WebhookDeliveryListResponse",
    "WebhookEventPublishRequest",
    "WebhookEventPublishResponse",
    "WebhookEventsResponse",
    "WebhookSignatureVerifyRequest",
    "WebhookSignatureVerifyResponse",
    "WebhookSubscriptionCreate",
    "WebhookSubscriptionListResponse",
    "WebhookSubscriptionResponse",
    "WebhookSubscriptionUpdate",
    "WebhookTestRequest",
    "WebhookTestResponse",
]
