"""通知 API — Phase 5 B23.

依据 docs/ROADMAP.md Phase 5 B23:

- ``GET  /api/v1/{tenant}/notifications/templates`` — 列出预置模板
- ``GET  /api/v1/{tenant}/notifications/configs`` — 列出当前租户通知配置
- ``POST /api/v1/{tenant}/notifications/configs`` — 新增配置
- ``POST /api/v1/{tenant}/notifications/test`` — 测试发送 (dry_run)
- ``GET  /api/v1/{tenant}/notifications/logs`` — 发送历史
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Query
from sqlalchemy import select

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep
from hscredit_studio.models import NotificationConfig, NotificationLog
from hscredit_studio.services.notification import (
    TEMPLATES,
    NotificationChannel,
    send_notification,
)

router = APIRouter(tags=["通知"])


@router.get("/templates", summary="预置通知模板列表")
async def list_templates() -> dict[str, Any]:
    """Phase 5 B23 — 列出预置通知模板."""
    return {
        "templates": [
            {
                "key": k,
                "title_template": v.title_template,
                "body_template": v.body_template,
                "default_channels": [c.value for c in v.default_channels],
            }
            for k, v in TEMPLATES.items()
        ],
        "count": len(TEMPLATES),
    }


@router.get("/configs", summary="租户通知配置列表")
async def list_configs(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
) -> dict[str, Any]:
    """列出租户通知配置."""
    tid = UUID(tenant_id)
    configs = (
        await session.execute(
            select(NotificationConfig)
            .where(NotificationConfig.tenant_id == tid)
            .order_by(NotificationConfig.created_at.desc())
        )
    ).scalars().all()
    return {
        "items": [
            {
                "config_id": str(c.config_id),
                "channel": c.channel,
                "template_key": c.template_key,
                "recipient": c.recipient,
                "enabled": c.enabled,
                "created_at": c.created_at.isoformat(),
            }
            for c in configs
        ],
        "count": len(configs),
    }


@router.post("/configs", summary="新增通知配置")
async def create_config(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    channel: str = Query(..., pattern="^(slack|wecom|email)$"),
    template_key: str | None = Query(default=None, description="None=接收全模板"),
    recipient: str | None = Query(default=None, description="邮件地址 / webhook URL override"),
    enabled: bool = Query(default=True),
) -> dict[str, Any]:
    """Phase 5 B23 — 新增租户通知配置."""
    tid = UUID(tenant_id)
    cfg = NotificationConfig(
        tenant_id=tid,
        channel=channel,
        template_key=template_key,
        recipient=recipient,
        enabled=enabled,
    )
    session.add(cfg)
    await session.commit()
    await session.refresh(cfg)
    return {
        "config_id": str(cfg.config_id),
        "channel": cfg.channel,
        "template_key": cfg.template_key,
        "recipient": cfg.recipient,
        "enabled": cfg.enabled,
    }


@router.post("/test", summary="测试发送 (dry_run)")
async def test_notification(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    template_key: str = Query(..., description="模板键"),
    channel: str = Query(default="email", pattern="^(slack|wecom|email)$"),
    recipient: str | None = Query(default=None),
    variables: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    """Phase 5 B23 — 测试通知发送 (dry_run=True 不真正发送).

    用于前端"测试通知配置"功能。
    """
    if template_key not in TEMPLATES:
        raise HTTPException(status_code=400, detail=f"模板不存在: {template_key}")

    tid = UUID(tenant_id)
    results = await send_notification(
        template_key=template_key,
        variables=variables or {
            "tenant_name": "测试租户",
            "billing_period": "2026-08",
            "plan": "pro",
            "total_amount": 199.0,
            "due_date": "2026-09-26",
            "bill_id": "test",
            "ratio": 0.85,
            "dimension": "runs",
            "used": 170,
            "limit": 200,
        },
        channels=[NotificationChannel(channel)],
        tenant_id=tid,
        recipient=recipient,
        dry_run=True,
    )
    # 写 NotificationLog (dry_run)
    log_entry = NotificationLog(
        tenant_id=tid,
        template_key=template_key,
        channel=channel,
        status="dry_run",
        title=results[0].error if (results and not results[0].success) else f"测试通知: {template_key}",
        body=str(variables),
        recipient=recipient,
        error=results[0].error if results and not results[0].success else None,
    )
    session.add(log_entry)
    await session.commit()

    return {
        "results": [
            {
                "channel": r.channel.value,
                "success": r.success,
                "dry_run": r.dry_run,
                "error": r.error,
            }
            for r in results
        ],
        "log_id": str(log_entry.log_id),
    }


@router.get("/logs", summary="发送历史")
async def list_logs(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    limit: int = Query(default=50, ge=1, le=200),
    template_key: str | None = None,
    channel: str | None = None,
) -> dict[str, Any]:
    """列出租户通知发送历史."""
    tid = UUID(tenant_id)
    stmt = select(NotificationLog).where(NotificationLog.tenant_id == tid)
    if template_key:
        stmt = stmt.where(NotificationLog.template_key == template_key)
    if channel:
        stmt = stmt.where(NotificationLog.channel == channel)
    stmt = stmt.order_by(NotificationLog.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "items": [
            {
                "log_id": str(r.log_id),
                "template_key": r.template_key,
                "channel": r.channel,
                "status": r.status,
                "title": r.title,
                "recipient": r.recipient,
                "error": r.error,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "count": len(rows),
    }


__all__ = ["router"]
