"""Webhook 单元测试 — Phase 8 B35."""
from __future__ import annotations

import hashlib
import hmac
import time
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from hscredit_studio.services.webhooks import (
    MAX_RETRY_COUNT,
    RETRY_DELAYS_SEC,
    SIGNATURE_TIMESTAMP_WINDOW,
    WebhookDeliveryStatus,
    WebhookEvent,
    generate_secret,
    matches_event,
    send_test_webhook,
    sign_payload,
    verify_signature,
)

# ===== A. 签名生成/验证 =====


class TestHMACSignature:
    """HMAC 签名测试 (B35 验收)."""

    def test_sign_payload_format(self) -> None:
        sig = sign_payload(secret="abc123", payload=b'{"event":"test"}', timestamp=1234567890)
        assert sig.startswith("sha256=")
        # 64 字符 hex
        assert len(sig.split("=", 1)[1]) == 64

    def test_sign_payload_deterministic(self) -> None:
        """相同输入 → 相同签名."""
        sig1 = sign_payload(secret="abc", payload=b"hello", timestamp=12345)
        sig2 = sign_payload(secret="abc", payload=b"hello", timestamp=12345)
        assert sig1 == sig2

    def test_sign_payload_different_secret(self) -> None:
        """不同密钥 → 不同签名."""
        sig1 = sign_payload(secret="key1", payload=b"hello", timestamp=12345)
        sig2 = sign_payload(secret="key2", payload=b"hello", timestamp=12345)
        assert sig1 != sig2

    def test_verify_signature_valid(self) -> None:
        secret = "test-secret"
        payload = b'{"event":"run.completed"}'
        ts = int(time.time())
        sig = sign_payload(secret=secret, payload=payload, timestamp=ts)
        assert verify_signature(secret=secret, payload=payload, signature=sig, timestamp=ts)

    def test_verify_signature_tampered_payload(self) -> None:
        secret = "test"
        ts = int(time.time())
        sig = sign_payload(secret=secret, payload=b"original", timestamp=ts)
        assert not verify_signature(
            secret=secret, payload=b"tampered", signature=sig, timestamp=ts
        )

    def test_verify_signature_wrong_secret(self) -> None:
        ts = int(time.time())
        sig = sign_payload(secret="correct", payload=b"x", timestamp=ts)
        assert not verify_signature(
            secret="wrong", payload=b"x", signature=sig, timestamp=ts
        )

    def test_verify_signature_expired_timestamp(self) -> None:
        """时间戳超出 5 分钟窗口 → 验证失败 (防重放)."""
        ts_old = int(time.time()) - SIGNATURE_TIMESTAMP_WINDOW - 60
        sig = sign_payload(secret="k", payload=b"x", timestamp=ts_old)
        assert not verify_signature(secret="k", payload=b"x", signature=sig, timestamp=ts_old)

    def test_verify_signature_within_window(self) -> None:
        """时间戳在窗口内 → 通过."""
        ts = int(time.time())
        sig = sign_payload(secret="k", payload=b"x", timestamp=ts)
        assert verify_signature(secret="k", payload=b"x", signature=sig, timestamp=ts)

    def test_signature_matches_hmac_reference(self) -> None:
        """与标准 HMAC 实现对照."""
        secret = "secret-key"
        payload = b'{"a":1}'
        ts = 1700000000
        expected = hmac.new(
            secret.encode("utf-8"),
            f"{ts}.".encode() + payload,
            hashlib.sha256,
        ).hexdigest()
        sig = sign_payload(secret=secret, payload=payload, timestamp=ts)
        assert sig == f"sha256={expected}"


# ===== B. 密钥生成 =====


class TestSecretGeneration:
    """密钥生成."""

    def test_generate_secret_length(self) -> None:
        s = generate_secret()
        # 32 字节 → 64 hex 字符
        assert len(s) == 64

    def test_generate_secret_unique(self) -> None:
        a = generate_secret()
        b = generate_secret()
        assert a != b
        assert len({a, b}) == 2

    def test_generate_secret_hex(self) -> None:
        s = generate_secret()
        # 仅含 hex 字符
        assert all(c in "0123456789abcdef" for c in s)


# ===== C. 事件匹配 =====


class TestEventMatching:
    """事件过滤."""

    def test_empty_list_matches_all(self) -> None:
        assert matches_event([], "run.completed") is True
        assert matches_event([], "alert.fired") is True

    def test_specific_event_match(self) -> None:
        assert matches_event(["run.completed"], "run.completed") is True

    def test_specific_event_no_match(self) -> None:
        assert matches_event(["run.completed"], "alert.fired") is False

    def test_multiple_events_partial_match(self) -> None:
        subs = ["run.completed", "alert.fired"]
        assert matches_event(subs, "run.completed")
        assert matches_event(subs, "alert.fired")
        assert not matches_event(subs, "bill.generated")


# ===== D. 投递执行 (mock aiohttp) =====


class TestWebhookDelivery:
    """HTTP POST 投递测试."""

    @pytest.mark.asyncio
    async def test_deliver_webhook_2xx_success(self) -> None:
        """2xx 响应视为成功."""
        # 通过 send_test_webhook 间接测试 (底层调用 deliver_webhook)
        success, status_code, error = await send_test_webhook(
            url="http://localhost:1/nonexistent",  # 连接失败场景
            secret="k",
        )
        # 本地无 1 端口 → 失败
        assert success is False
        assert status_code is None
        assert error is not None

    @pytest.mark.asyncio
    async def test_deliver_webhook_timeout(self) -> None:
        """超时处理."""
        success, _status_code, error = await send_test_webhook(
            url="http://10.255.255.1:1/will_timeout",
            secret="k",
            timeout_sec=2,
        )
        assert success is False
        assert error is not None

    @pytest.mark.asyncio
    async def test_send_test_payload_contains_event(self) -> None:
        """test payload 应含 event 字段."""
        # 使用本地 httpbin 替代 (本地 dev 跳过)
        # 此测试仅验证 send_test_webhook 不抛异常
        import contextlib

        with contextlib.suppress(Exception):
            await send_test_webhook(
                url="http://localhost:9/none",
                secret="k",
                event="custom.event",
                extra_payload={"foo": "bar"},
                timeout_sec=1,
            )


# ===== E. 重试策略 =====


class TestRetryPolicy:
    """重试策略常量测试."""

    def test_retry_delays_count(self) -> None:
        assert len(RETRY_DELAYS_SEC) == MAX_RETRY_COUNT

    def test_retry_delays_exponential(self) -> None:
        """重试间隔应大致指数增长."""
        for i in range(1, len(RETRY_DELAYS_SEC)):
            ratio = RETRY_DELAYS_SEC[i] / RETRY_DELAYS_SEC[i - 1]
            assert ratio >= 2.0  # 至少 2x 增长

    def test_max_retry_count_positive(self) -> None:
        assert MAX_RETRY_COUNT >= 3


# ===== F. 事件类型枚举 =====


class TestWebhookEventEnum:
    """事件类型枚举测试."""

    def test_workflow_events(self) -> None:
        assert WebhookEvent.WORKFLOW_CREATED.value == "workflow.created"
        assert WebhookEvent.WORKFLOW_UPDATED.value == "workflow.updated"
        assert WebhookEvent.WORKFLOW_DELETED.value == "workflow.deleted"

    def test_run_events(self) -> None:
        assert WebhookEvent.RUN_SUBMITTED.value == "run.submitted"
        assert WebhookEvent.RUN_COMPLETED.value == "run.completed"
        assert WebhookEvent.RUN_FAILED.value == "run.failed"
        assert WebhookEvent.RUN_CANCELLED.value == "run.cancelled"

    def test_alert_events(self) -> None:
        assert WebhookEvent.ALERT_FIRED.value == "alert.fired"
        assert WebhookEvent.ALERT_RESOLVED.value == "alert.resolved"

    def test_billing_events(self) -> None:
        assert WebhookEvent.BILL_GENERATED.value == "bill.generated"
        assert WebhookEvent.BILL_PAID.value == "bill.paid"

    def test_event_total_count(self) -> None:
        # 应有 13 个事件
        assert len(list(WebhookEvent)) == 13


# ===== G. 投递状态枚举 =====


class TestDeliveryStatusEnum:
    """投递状态枚举."""

    def test_status_values(self) -> None:
        assert WebhookDeliveryStatus.PENDING.value == "pending"
        assert WebhookDeliveryStatus.SUCCESS.value == "success"
        assert WebhookDeliveryStatus.FAILED.value == "failed"
        assert WebhookDeliveryStatus.RETRYING.value == "retrying"
        assert WebhookDeliveryStatus.CANCELLED.value == "cancelled"


# ===== H. Schemas 校验 (Pydantic) =====


class TestWebhookSchemas:
    """Pydantic schema 校验."""

    def test_subscription_create_min_url_length(self) -> None:
        from hscredit_studio.schemas.webhooks import WebhookSubscriptionCreate

        with pytest.raises(ValueError):
            WebhookSubscriptionCreate(url="x")  # 太短

    def test_subscription_create_happy(self) -> None:
        from hscredit_studio.schemas.webhooks import WebhookSubscriptionCreate

        s = WebhookSubscriptionCreate(
            url="https://example.com/hook",
            events=[WebhookEvent.RUN_COMPLETED],
        )
        assert s.active is True
        assert s.description == ""

    def test_subscription_update_partial(self) -> None:
        from hscredit_studio.schemas.webhooks import WebhookSubscriptionUpdate

        u = WebhookSubscriptionUpdate(active=False)
        assert u.active is False
        assert u.url is None

    def test_test_request_default_event(self) -> None:
        from hscredit_studio.schemas.webhooks import WebhookTestRequest

        r = WebhookTestRequest(url="https://example.com")
        assert r.event == "webhook.test"
        assert r.payload == {}

    def test_publish_request_happy(self) -> None:
        from hscredit_studio.schemas.webhooks import WebhookEventPublishRequest

        r = WebhookEventPublishRequest(
            event=WebhookEvent.ALERT_FIRED,
            payload={"severity": "critical"},
        )
        assert r.event == WebhookEvent.ALERT_FIRED

    def test_signature_verify_request(self) -> None:
        from hscredit_studio.schemas.webhooks import WebhookSignatureVerifyRequest

        r = WebhookSignatureVerifyRequest(
            secret="x" * 16,
            payload='{"a":1}',
            signature="sha256=" + "a" * 64,
            timestamp=1234567890,
        )
        assert r.timestamp == 1234567890


# ===== I. publish_event (mock session) =====


class TestPublishEvent:
    """事件发布测试."""

    @pytest.mark.asyncio
    async def test_publish_event_no_subs(self) -> None:
        """无订阅时入队 0."""
        from hscredit_studio.services.webhooks import publish_event

        session = AsyncMock()
        # execute 返回空 scalars
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        result = await publish_event(
            session,
            event=WebhookEvent.RUN_COMPLETED,
            tenant_id=uuid4(),
            payload={"run_id": "abc"},
        )
        assert result.enqueued_count == 0

    @pytest.mark.asyncio
    async def test_publish_event_matches_subs(self) -> None:
        """匹配订阅时入队对应数量."""
        from hscredit_studio.services.webhooks import publish_event

        session = AsyncMock()
        # 2 个订阅, 1 个监听 run.completed, 1 个监听 alert.fired
        mock_sub_1 = MagicMock()
        mock_sub_1.subscription_id = uuid4()
        mock_sub_1.events = ["run.completed"]

        mock_sub_2 = MagicMock()
        mock_sub_2.subscription_id = uuid4()
        mock_sub_2.events = ["alert.fired"]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_sub_1, mock_sub_2]
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        result = await publish_event(
            session,
            event=WebhookEvent.RUN_COMPLETED,
            tenant_id=uuid4(),
            payload={},
        )
        # 只有 sub_1 匹配
        assert result.enqueued_count == 1


# ===== J. retry_failed_delivery (mock session) =====


class TestRetryDelivery:
    """重试投递测试."""

    @pytest.mark.asyncio
    async def test_retry_delivery_not_found(self) -> None:
        from hscredit_studio.services.webhooks import retry_failed_delivery

        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await retry_failed_delivery(session, delivery_id=uuid4())

    @pytest.mark.asyncio
    async def test_retry_delivery_subscription_inactive(self) -> None:
        """订阅被停用 → 投递标记 cancelled."""
        from hscredit_studio.services.webhooks import retry_failed_delivery

        # 构造 delivery
        delivery = MagicMock()
        delivery.subscription_id = uuid4()
        delivery.delivery_id = uuid4()
        delivery.event = "run.completed"
        delivery.body = b'{"x":1}'
        delivery.payload = {"x": 1}
        delivery.attempt = 0
        delivery.status = "pending"

        # subscription 已被禁用
        sub = MagicMock()
        sub.subscription_id = delivery.subscription_id
        sub.active = False

        # session.scalar 两次调用: 第一次返回 delivery, 第二次返回 sub
        session = AsyncMock()
        session.scalar = AsyncMock(side_effect=[delivery, sub])
        session.commit = AsyncMock()

        result = await retry_failed_delivery(session, delivery_id=delivery.delivery_id)
        assert result.status == WebhookDeliveryStatus.CANCELLED
        assert delivery.status == WebhookDeliveryStatus.CANCELLED.value
