"""Webhook API — Phase 8 B35.

依据 docs/ROADMAP.md Phase 8 B35:

| 端点 | 方法 | 用途 |
|---|---|---|
| /webhooks/events | GET | 列出支持的事件类型 |
| /webhooks/subscriptions | POST | 创建订阅 |
| /webhooks/subscriptions | GET | 列出订阅 |
| /webhooks/subscriptions/{id} | GET | 订阅详情 |
| /webhooks/subscriptions/{id} | PATCH | 更新订阅 |
| /webhooks/subscriptions/{id} | DELETE | 删除订阅 |
| /webhooks/subscriptions/{id}/test | POST | 测试投递 |
| /webhooks/subscriptions/{id}/deliveries | GET | 投递日志 |
| /webhooks/deliveries/{id}/retry | POST | 手动重试 |
| /webhooks/publish | POST | 内部发布事件 (供其他模块触发) |
| /webhooks/verify-signature | POST | 验证 HMAC 签名 (供租户调试) |
"""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Path, Query, status
from sqlalchemy import and_, select

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep
from hscredit_studio.models.webhook import WebhookDelivery, WebhookSubscription
from hscredit_studio.schemas.webhooks import (
    WebhookDeliveryItem,
    WebhookDeliveryListResponse,
    WebhookEventPublishRequest,
    WebhookEventPublishResponse,
    WebhookEventsResponse,
    WebhookSignatureVerifyRequest,
    WebhookSignatureVerifyResponse,
    WebhookSubscriptionCreate,
    WebhookSubscriptionListResponse,
    WebhookSubscriptionResponse,
    WebhookSubscriptionUpdate,
    WebhookTestRequest,
    WebhookTestResponse,
)
from hscredit_studio.services import webhooks as svc

router = APIRouter(tags=["Webhook"])


@router.get(
    "/events",
    response_model=WebhookEventsResponse,
    summary="列出 Webhook 支持的事件类型 (B35)",
)
async def list_events(_: CurrentUserDep) -> WebhookEventsResponse:
    items = [
        {
            "event": e.value,
            "category": e.value.split(".")[0],
            "description": _EVENT_DESCRIPTIONS.get(e, ""),
        }
        for e in svc.WebhookEvent
    ]
    return WebhookEventsResponse(events=items, total=len(items))


_EVENT_DESCRIPTIONS: dict[svc.WebhookEvent, str] = {
    svc.WebhookEvent.WORKFLOW_CREATED: "工作流创建",
    svc.WebhookEvent.WORKFLOW_UPDATED: "工作流更新",
    svc.WebhookEvent.WORKFLOW_DELETED: "工作流删除",
    svc.WebhookEvent.RUN_SUBMITTED: "Run 提交",
    svc.WebhookEvent.RUN_COMPLETED: "Run 完成",
    svc.WebhookEvent.RUN_FAILED: "Run 失败",
    svc.WebhookEvent.RUN_CANCELLED: "Run 取消",
    svc.WebhookEvent.ALERT_FIRED: "告警触发",
    svc.WebhookEvent.ALERT_RESOLVED: "告警恢复",
    svc.WebhookEvent.BILL_GENERATED: "账单生成",
    svc.WebhookEvent.BILL_PAID: "账单支付",
    svc.WebhookEvent.TEMPLATE_SHARED: "模板共享",
    svc.WebhookEvent.TEMPLATE_APPROVED: "模板审核通过",
}


@router.post(
    "/subscriptions",
    response_model=WebhookSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Webhook 订阅 (B35 验收)",
)
async def create_subscription(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    body: WebhookSubscriptionCreate,
) -> WebhookSubscriptionResponse:
    """创建 webhook 订阅, 自动生成 32 字节密钥.

    secret 仅在创建时返回, 后续 GET 不会泄露.
    """
    tenant_uuid = UUID(tenant_id)
    secret = svc.generate_secret()

    sub = WebhookSubscription(
        subscription_id=uuid4(),
        tenant_id=tenant_uuid,
        url=body.url,
        secret=secret,
        events=[e.value for e in body.events],
        active=body.active,
        description=body.description,
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)

    return WebhookSubscriptionResponse(
        subscription_id=str(sub.subscription_id),
        tenant_id=str(sub.tenant_id),
        url=sub.url,
        events=sub.events or [],
        active=sub.active,
        description=sub.description,
        created_at=sub.created_at,
        secret=secret,
    )


@router.get(
    "/subscriptions",
    response_model=WebhookSubscriptionListResponse,
    summary="列出 Webhook 订阅",
)
async def list_subscriptions(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
) -> WebhookSubscriptionListResponse:
    tenant_uuid = UUID(tenant_id)
    rows = (
        await session.execute(
            select(WebhookSubscription).where(WebhookSubscription.tenant_id == tenant_uuid)
        )
    ).scalars().all()
    items = [
        WebhookSubscriptionResponse(
            subscription_id=str(r.subscription_id),
            tenant_id=str(r.tenant_id),
            url=r.url,
            events=r.events or [],
            active=r.active,
            description=r.description,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return WebhookSubscriptionListResponse(items=items, total=len(items))


@router.get(
    "/subscriptions/{subscription_id}",
    response_model=WebhookSubscriptionResponse,
    summary="Webhook 订阅详情",
)
async def get_subscription(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    subscription_id: UUID = Path(...),
) -> WebhookSubscriptionResponse:
    tenant_uuid = UUID(tenant_id)
    sub = await session.scalar(
        select(WebhookSubscription).where(
            and_(
                WebhookSubscription.tenant_id == tenant_uuid,
                WebhookSubscription.subscription_id == subscription_id,
            )
        )
    )
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "E_NOT_FOUND", "message": "订阅不存在"},
        )
    return WebhookSubscriptionResponse(
        subscription_id=str(sub.subscription_id),
        tenant_id=str(sub.tenant_id),
        url=sub.url,
        events=sub.events or [],
        active=sub.active,
        description=sub.description,
        created_at=sub.created_at,
    )


@router.patch(
    "/subscriptions/{subscription_id}",
    response_model=WebhookSubscriptionResponse,
    summary="更新 Webhook 订阅",
)
async def update_subscription(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    subscription_id: UUID = Path(...),
    body: WebhookSubscriptionUpdate | None = None,
) -> WebhookSubscriptionResponse:
    tenant_uuid = UUID(tenant_id)
    sub = await session.scalar(
        select(WebhookSubscription).where(
            and_(
                WebhookSubscription.tenant_id == tenant_uuid,
                WebhookSubscription.subscription_id == subscription_id,
            )
        )
    )
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "E_NOT_FOUND", "message": "订阅不存在"},
        )

    if body is not None:
        if body.url is not None:
            sub.url = body.url
        if body.events is not None:
            sub.events = [e.value for e in body.events]
        if body.active is not None:
            sub.active = body.active
        if body.description is not None:
            sub.description = body.description
    await session.commit()
    await session.refresh(sub)
    return WebhookSubscriptionResponse(
        subscription_id=str(sub.subscription_id),
        tenant_id=str(sub.tenant_id),
        url=sub.url,
        events=sub.events or [],
        active=sub.active,
        description=sub.description,
        created_at=sub.created_at,
    )


@router.delete(
    "/subscriptions/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除 Webhook 订阅",
)
async def delete_subscription(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    subscription_id: UUID = Path(...),
) -> None:
    tenant_uuid = UUID(tenant_id)
    sub = await session.scalar(
        select(WebhookSubscription).where(
            and_(
                WebhookSubscription.tenant_id == tenant_uuid,
                WebhookSubscription.subscription_id == subscription_id,
            )
        )
    )
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "E_NOT_FOUND", "message": "订阅不存在"},
        )
    await session.delete(sub)
    await session.commit()


@router.post(
    "/subscriptions/{subscription_id}/test",
    response_model=WebhookTestResponse,
    summary="测试 Webhook 投递 (B35 验收)",
)
async def test_subscription(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    subscription_id: UUID = Path(...),
) -> WebhookTestResponse:
    """向订阅 URL 发送测试事件, 验证连通性 + HMAC 签名.

    用于租户配置订阅后立即验证 endpoint 是否正确.
    """
    tenant_uuid = UUID(tenant_id)
    sub = await session.scalar(
        select(WebhookSubscription).where(
            and_(
                WebhookSubscription.tenant_id == tenant_uuid,
                WebhookSubscription.subscription_id == subscription_id,
            )
        )
    )
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "E_NOT_FOUND", "message": "订阅不存在"},
        )

    delivery_id = uuid4()
    success, status_code, error = await svc.send_test_webhook(
        url=sub.url,
        secret=sub.secret,
        event="webhook.test",
    )
    return WebhookTestResponse(
        success=success,
        response_status=status_code,
        error=error,
        secret_used=sub.secret,
        delivery_id=str(delivery_id),
    )


@router.post(
    "/test",
    response_model=WebhookTestResponse,
    summary="测试任意 URL 的 Webhook 投递 (无需订阅)",
)
async def test_url(
    _: CurrentUserDep,
    body: WebhookTestRequest,
) -> WebhookTestResponse:
    """测试任意 URL 是否能接收 Webhook (无需先创建订阅)."""
    secret = body.secret or svc.generate_secret()
    delivery_id = uuid4()
    success, status_code, error = await svc.send_test_webhook(
        url=body.url,
        secret=secret,
        event=body.event,
        extra_payload=body.payload,
    )
    return WebhookTestResponse(
        success=success,
        response_status=status_code,
        error=error,
        secret_used=secret,
        delivery_id=str(delivery_id),
    )


@router.get(
    "/subscriptions/{subscription_id}/deliveries",
    response_model=WebhookDeliveryListResponse,
    summary="Webhook 投递日志 (B35)",
)
async def list_deliveries(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    subscription_id: UUID = Path(...),
    page: int = Query(default=1, ge=1, le=1000),
    page_size: int = Query(default=50, ge=1, le=500),
    status_filter: str | None = Query(default=None, alias="status"),
) -> WebhookDeliveryListResponse:
    tenant_uuid = UUID(tenant_id)
    sub = await session.scalar(
        select(WebhookSubscription).where(
            and_(
                WebhookSubscription.tenant_id == tenant_uuid,
                WebhookSubscription.subscription_id == subscription_id,
            )
        )
    )
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "E_NOT_FOUND", "message": "订阅不存在"},
        )

    stmt = select(WebhookDelivery).where(
        WebhookDelivery.subscription_id == subscription_id
    )
    if status_filter:
        stmt = stmt.where(WebhookDelivery.status == status_filter)
    stmt = stmt.order_by(WebhookDelivery.created_at.desc())
    stmt = stmt.limit(page_size).offset((page - 1) * page_size)

    rows = (await session.execute(stmt)).scalars().all()
    items = [
        WebhookDeliveryItem(
            delivery_id=str(r.delivery_id),
            subscription_id=str(r.subscription_id),
            event=r.event,
            status=svc.WebhookDeliveryStatus(r.status),
            attempt=r.attempt,
            response_status=r.response_status,
            last_error=r.last_error,
            scheduled_at=r.scheduled_at,
            delivered_at=r.delivered_at,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return WebhookDeliveryListResponse(items=items, total=len(items))


@router.post(
    "/deliveries/{delivery_id}/retry",
    response_model=WebhookDeliveryItem,
    summary="手动重试 Webhook 投递 (B35)",
)
async def retry_delivery(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    delivery_id: UUID = Path(...),
) -> WebhookDeliveryItem:
    tenant_uuid = UUID(tenant_id)
    delivery = await session.scalar(
        select(WebhookDelivery).where(
            and_(
                WebhookDelivery.tenant_id == tenant_uuid,
                WebhookDelivery.delivery_id == delivery_id,
            )
        )
    )
    if delivery is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "E_NOT_FOUND", "message": "投递不存在"},
        )

    await svc.retry_failed_delivery(session, delivery_id=delivery_id)
    await session.refresh(delivery)
    return WebhookDeliveryItem(
        delivery_id=str(delivery.delivery_id),
        subscription_id=str(delivery.subscription_id),
        event=delivery.event,
        status=svc.WebhookDeliveryStatus(delivery.status),
        attempt=delivery.attempt,
        response_status=delivery.response_status,
        last_error=delivery.last_error,
        scheduled_at=delivery.scheduled_at,
        delivered_at=delivery.delivered_at,
        created_at=delivery.created_at,
    )


@router.post(
    "/publish",
    response_model=WebhookEventPublishResponse,
    summary="发布 Webhook 事件 (内部 API)",
)
async def publish_event(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    body: WebhookEventPublishRequest,
) -> WebhookEventPublishResponse:
    """发布事件 → 自动匹配订阅 → 入队投递.

    供其他模块 (Run 完成 / 告警触发 / 账单生成) 调用.
    """
    tenant_uuid = UUID(tenant_id)
    result = await svc.publish_event(
        session,
        event=body.event,
        tenant_id=tenant_uuid,
        payload=body.payload,
    )
    return WebhookEventPublishResponse(
        event_id=str(result.event_id),
        event=result.event,
        tenant_id=str(result.tenant_id),
        enqueued_count=result.enqueued_count,
        published_at=result.published_at,
    )


@router.post(
    "/verify-signature",
    response_model=WebhookSignatureVerifyResponse,
    summary="验证 Webhook HMAC 签名 (B35 调试工具)",
)
async def verify_signature_endpoint(
    _: CurrentUserDep,
    body: WebhookSignatureVerifyRequest,
) -> WebhookSignatureVerifyResponse:
    """供租户端调试 webhook 签名验证逻辑."""
    valid = svc.verify_signature(
        secret=body.secret,
        payload=body.payload.encode("utf-8"),
        signature=body.signature,
        timestamp=body.timestamp,
    )
    if not valid:
        return WebhookSignatureVerifyResponse(
            valid=False,
            reason="签名不匹配或时间戳超出 5 分钟窗口",
        )
    return WebhookSignatureVerifyResponse(valid=True)


__all__ = ["router"]
