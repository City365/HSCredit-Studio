"""Webhook 投递系统 — Phase 8 B35.

设计:

- :class:`WebhookEvent` — 事件类型枚举
- :class:`WebhookSubscription` — 订阅 (URL + secret + 事件过滤)
- :class:`WebhookDelivery` — 单次投递尝试 (status + response)
- :func:`sign_payload` — HMAC-SHA256 签名 (X-HSCredit-Signature 头)
- :func:`publish_event` — 发布事件 → 查询订阅 → 入队投递
- :func:`deliver_webhook` — 实际 HTTP POST (aiohttp, 含重试)
- :func:`retry_failed_deliveries` — 后台任务扫描失败投递, 指数退避

Webhook 与现有通知 (B23) 的区别:

- B23 通知: 平台 → 用户 (Slack/WeCom/SMTP, 推送消息给运维)
- B27 Webhook: Alertmanager → 平台 (入站告警接收)
- B35 Webhook: 平台 → 租户系统 (出站事件投递, HTTP POST + HMAC 验签)

安全:

- 每个 subscription 有独立 secret (32 字节随机)
- HMAC-SHA256 签名防止伪造
- 投递 body 含时间戳, 防重放 (5 分钟窗口)
- 失败重试: 指数退避 1min / 5min / 30min / 2h / 12h
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

import aiohttp
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.logging import get_logger

_log = get_logger(__name__)


class WebhookEvent(StrEnum):
    """Webhook 事件类型 (Phase 8 B35)."""

    WORKFLOW_CREATED = "workflow.created"
    WORKFLOW_UPDATED = "workflow.updated"
    WORKFLOW_DELETED = "workflow.deleted"
    RUN_SUBMITTED = "run.submitted"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    ALERT_FIRED = "alert.fired"
    ALERT_RESOLVED = "alert.resolved"
    BILL_GENERATED = "bill.generated"
    BILL_PAID = "bill.paid"
    TEMPLATE_SHARED = "template.shared"
    TEMPLATE_APPROVED = "template.approved"


class WebhookDeliveryStatus(StrEnum):
    """Webhook 投递状态."""

    PENDING = "pending"      # 已入队, 待投递
    SUCCESS = "success"      # 2xx 响应
    FAILED = "failed"        # 重试耗尽或 4xx (非 408/429)
    RETRYING = "retrying"    # 失败后等待重试
    CANCELLED = "cancelled"  # 订阅被删除


# 重试间隔 (秒): 1min / 5min / 30min / 2h / 12h
RETRY_DELAYS_SEC: list[int] = [60, 300, 1800, 7200, 43200]
MAX_RETRY_COUNT = 5

# 签名校验时间窗口 (秒)
SIGNATURE_TIMESTAMP_WINDOW = 300


@dataclass
class WebhookSubscriptionSpec:
    """Webhook 订阅规范 (Phase 8 B35).

    Attributes:
        subscription_id: 订阅 UUID.
        tenant_id: 租户 ID.
        url: 目标 URL.
        secret: HMAC 签名密钥.
        events: 订阅的事件列表 (空 = 全部).
        active: 是否启用.
        description: 描述.
    """

    subscription_id: UUID
    tenant_id: UUID
    url: str
    secret: str
    events: list[str] = field(default_factory=list)
    active: bool = True
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


@dataclass
class WebhookDeliverySpec:
    """Webhook 单次投递规范."""

    delivery_id: UUID
    subscription_id: UUID
    tenant_id: UUID
    event: str
    payload: dict[str, Any]
    attempt: int = 0
    status: WebhookDeliveryStatus = WebhookDeliveryStatus.PENDING
    last_error: str | None = None
    response_status: int | None = None
    response_body: str | None = None
    scheduled_at: datetime = field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    delivered_at: datetime | None = None


# ===== 签名 =====


def sign_payload(
    *,
    secret: str,
    payload: bytes,
    timestamp: int | None = None,
) -> str:
    """生成 HMAC-SHA256 签名 (Phase 8 B35).

    格式: ``sha256={hex_digest}``

    Args:
        secret: 订阅密钥.
        payload: 待签名的字节.
        timestamp: Unix 时间戳 (None = 当前时间).
    """
    if timestamp is None:
        timestamp = int(datetime.now(UTC).timestamp())
    signed_payload = f"{timestamp}.".encode() + payload
    digest = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def verify_signature(
    *,
    secret: str,
    payload: bytes,
    signature: str,
    timestamp: int,
    tolerance: int = SIGNATURE_TIMESTAMP_WINDOW,
) -> bool:
    """验证 HMAC 签名 + 时间窗口 (Phase 8 B35)."""
    now = int(datetime.now(UTC).timestamp())
    if abs(now - timestamp) > tolerance:
        return False
    expected = sign_payload(secret=secret, payload=payload, timestamp=timestamp)
    return hmac.compare_digest(expected, signature)


# ===== 订阅管理 =====


def generate_secret() -> str:
    """生成 32 字节随机密钥 (hex 64 字符)."""
    return secrets.token_hex(32)


def matches_event(
    subscription_events: list[str],
    event: str,
) -> bool:
    """判断订阅是否监听指定事件.

    空订阅列表 = 监听全部事件.
    """
    if not subscription_events:
        return True
    return event in subscription_events


# ===== 事件发布 =====


@dataclass
class PublishedEvent:
    """已发布事件 (Phase 8 B35)."""

    event_id: UUID
    event: WebhookEvent
    tenant_id: UUID
    payload: dict[str, Any]
    enqueued_count: int
    published_at: datetime = field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


async def publish_event(
    session: AsyncSession,
    *,
    event: WebhookEvent,
    tenant_id: UUID,
    payload: dict[str, Any],
) -> PublishedEvent:
    """发布事件 → 查找订阅 → 创建投递记录 (B35 验收).

    Args:
        session: 异步数据库 session.
        event: 事件类型.
        tenant_id: 租户 ID.
        payload: 事件负载 (JSON-serializable).

    Returns:
        :class:`PublishedEvent` 含事件 ID + 入队的投递数.
    """
    from hscredit_studio.models.webhook import (
        WebhookDelivery,
        WebhookSubscription,
    )

    event_id = uuid4()
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")

    # 查询启用且匹配事件的订阅
    stmt = select(WebhookSubscription).where(
        and_(
            WebhookSubscription.tenant_id == tenant_id,
            WebhookSubscription.active.is_(True),
        )
    )
    subs = (await session.execute(stmt)).scalars().all()

    enqueued = 0
    now = datetime.now(UTC).replace(tzinfo=None)
    for sub in subs:
        if not matches_event(sub.events or [], event.value):
            continue
        delivery = WebhookDelivery(
            delivery_id=uuid4(),
            subscription_id=sub.subscription_id,
            tenant_id=tenant_id,
            event=event.value,
            payload=payload,
            attempt=0,
            status=WebhookDeliveryStatus.PENDING.value,
            body=body,
            scheduled_at=now,
        )
        session.add(delivery)
        enqueued += 1

    await session.commit()
    _log.info(
        "webhook_event_published",
        event=event.value,
        tenant_id=str(tenant_id),
        event_id=str(event_id),
        enqueued=enqueued,
    )

    return PublishedEvent(
        event_id=event_id,
        event=event,
        tenant_id=tenant_id,
        payload=payload,
        enqueued_count=enqueued,
    )


# ===== 投递执行 =====


async def deliver_webhook(
    *,
    url: str,
    secret: str,
    event: str,
    body: bytes,
    delivery_id: UUID,
    timeout_sec: int = 10,
) -> tuple[bool, int | None, str | None]:
    """实际 HTTP POST 投递 (Phase 8 B35).

    Returns:
        (success, status_code, error_message).
    """
    timestamp = int(datetime.now(UTC).replace(tzinfo=None).timestamp())
    signature = sign_payload(secret=secret, payload=body, timestamp=timestamp)
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "HSCredit-Studio-Webhooks/1.0",
        "X-HSCredit-Event": event,
        "X-HSCredit-Delivery-Id": str(delivery_id),
        "X-HSCredit-Timestamp": str(timestamp),
        "X-HSCredit-Signature": signature,
    }

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                url,
                data=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout_sec),
            ) as resp,
        ):
            response_text = (await resp.text())[:500]
            success = 200 <= resp.status < 300
            return success, resp.status, response_text if not success else None
    except Exception as e:
        return False, None, f"{type(e).__name__}: {e}"[:500]


async def retry_failed_delivery(
    session: AsyncSession,
    *,
    delivery_id: UUID,
) -> WebhookDeliverySpec:
    """重试一次失败投递 (B35).

    1. 读取 delivery + subscription
    2. 计算下次重试时间 (指数退避)
    3. 调用 deliver_webhook
    4. 写回结果

    Returns:
        更新后的 :class:`WebhookDeliverySpec`.
    """
    from hscredit_studio.models.webhook import (
        WebhookDelivery,
        WebhookSubscription,
    )

    delivery = await session.scalar(
        select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id)
    )
    if delivery is None:
        raise ValueError(f"Delivery {delivery_id} not found")

    subscription = await session.scalar(
        select(WebhookSubscription).where(
            WebhookSubscription.subscription_id == delivery.subscription_id,
        )
    )
    if subscription is None or not subscription.active:
        delivery.status = WebhookDeliveryStatus.CANCELLED.value
        delivery.last_error = "subscription inactive or removed"
        await session.commit()
        return _to_spec(delivery)

    body = delivery.body or json.dumps(delivery.payload or {}).encode("utf-8")
    success, status_code, error = await deliver_webhook(
        url=subscription.url,
        secret=subscription.secret,
        event=delivery.event,
        body=body,
        delivery_id=delivery.delivery_id,
    )

    delivery.attempt += 1
    delivery.response_status = status_code
    delivery.response_body = (error or "")[:500]

    if success:
        delivery.status = WebhookDeliveryStatus.SUCCESS.value
        delivery.delivered_at = datetime.now(UTC).replace(tzinfo=None)
        delivery.last_error = None
    elif delivery.attempt >= MAX_RETRY_COUNT:
        delivery.status = WebhookDeliveryStatus.FAILED.value
        delivery.last_error = error
    else:
        # 计算下次重试时间
        delay = RETRY_DELAYS_SEC[min(delivery.attempt - 1, len(RETRY_DELAYS_SEC) - 1)]
        delivery.status = WebhookDeliveryStatus.RETRYING.value
        delivery.scheduled_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=delay)
        delivery.last_error = error

    await session.commit()
    return _to_spec(delivery)


def _to_spec(delivery: Any) -> WebhookDeliverySpec:
    """ORM → dataclass 转换."""
    return WebhookDeliverySpec(
        delivery_id=delivery.delivery_id,
        subscription_id=delivery.subscription_id,
        tenant_id=delivery.tenant_id,
        event=delivery.event,
        payload=delivery.payload or {},
        attempt=delivery.attempt,
        status=WebhookDeliveryStatus(delivery.status),
        last_error=delivery.last_error,
        response_status=delivery.response_status,
        response_body=delivery.response_body,
        scheduled_at=delivery.scheduled_at,
        delivered_at=delivery.delivered_at,
    )


async def send_test_webhook(
    *,
    url: str,
    secret: str,
    event: str = "webhook.test",
    extra_payload: dict[str, Any] | None = None,
    timeout_sec: int = 10,
) -> tuple[bool, int | None, str | None]:
    """发送测试 Webhook (B35 验收 — 租户配置订阅后立即验证).

    Returns:
        (success, status_code, error).
    """
    payload = {
        "event": event,
        "test": True,
        "timestamp": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        **(extra_payload or {}),
    }
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    delivery_id = uuid4()
    return await deliver_webhook(
        url=url,
        secret=secret,
        event=event,
        body=body,
        delivery_id=delivery_id,
        timeout_sec=timeout_sec,
    )


__all__ = [
    "MAX_RETRY_COUNT",
    "RETRY_DELAYS_SEC",
    "SIGNATURE_TIMESTAMP_WINDOW",
    "PublishedEvent",
    "WebhookDeliverySpec",
    "WebhookDeliveryStatus",
    "WebhookEvent",
    "WebhookSubscriptionSpec",
    "deliver_webhook",
    "generate_secret",
    "matches_event",
    "publish_event",
    "retry_failed_delivery",
    "send_test_webhook",
    "sign_payload",
    "verify_signature",
]
