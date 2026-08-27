"""审计事件 API 路由.

端点清单:

- ``GET    /audit-events``                — 审计事件分页查询
- ``GET    /audit-events/stats``          — 统计概览 (运营 Dashboard)
- ``GET    /audit-events/export``         — 流式 CSV 导出
- ``POST   /audit-events``                — 手动写入 (内部/管理用)

所有端点均需鉴权 (``CurrentUserDep``) + 租户隔离 (``TenantDep``).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep
from hscredit_studio.core.logging import get_logger
from hscredit_studio.models import AuditEvent, User
from hscredit_studio.schemas.audit import (
    AuditEventItem,
    AuditEventListResponse,
    AuditStats,
)
from hscredit_studio.services import audit as audit_service

router = APIRouter(tags=["审计"])
_log = get_logger(__name__)


@router.get(
    "",
    response_model=AuditEventListResponse,
    summary="审计事件分页查询",
    description=(
        "分页列出当前租户审计事件, 支持按动作 / 资源类型 / 用户 / 时间区间过滤. "
        "事件按 ``occurred_at DESC`` 排序 (最新优先)."
    ),
)
async def list_audit_events(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    user_id: UUID | None = Query(default=None, description="按用户过滤"),
    action: str | None = Query(default=None, description="按动作过滤 (login/workflow_create/...)"),
    resource_type: str | None = Query(default=None, description="按资源类型过滤"),
    resource_id: UUID | None = Query(default=None, description="按资源 ID 过滤"),
    since: datetime | None = Query(default=None, description="起始时间 (ISO 8601)"),
    until: datetime | None = Query(default=None, description="截止时间 (ISO 8601)"),
    page: int = Query(default=1, ge=1, le=1000, description="页码"),
    page_size: int = Query(default=50, ge=1, le=500, description="每页条数"),
) -> AuditEventListResponse:
    rows, total = await audit_service.list_events(
        session,
        UUID(tenant_id),
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        since=since,
        until=until,
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return AuditEventListResponse(
        items=[AuditEventItem.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/stats",
    response_model=AuditStats,
    summary="审计统计概览",
    description="返回租户审计统计 (活跃用户、Top 动作、Top 用户).",
)
async def audit_stats(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
) -> AuditStats:
    tenant_uuid = UUID(tenant_id)

    total_events = (
        await session.scalar(select(func.count(AuditEvent.event_id)).where(AuditEvent.tenant_id == tenant_uuid)) or 0
    )

    unique_users = (
        await session.scalar(
            select(func.count(func.distinct(AuditEvent.user_id))).where(
                AuditEvent.tenant_id == tenant_uuid,
                AuditEvent.user_id.is_not(None),
            )
        )
        or 0
    )

    unique_actions = (
        await session.scalar(
            select(func.count(func.distinct(AuditEvent.action))).where(AuditEvent.tenant_id == tenant_uuid)
        )
        or 0
    )

    from datetime import timedelta

    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    last_24h_events = (
        await session.scalar(
            select(func.count(AuditEvent.event_id)).where(
                AuditEvent.tenant_id == tenant_uuid,
                AuditEvent.occurred_at >= last_24h,
            )
        )
        or 0
    )

    last_7d_events = (
        await session.scalar(
            select(func.count(AuditEvent.event_id)).where(
                AuditEvent.tenant_id == tenant_uuid,
                AuditEvent.occurred_at >= last_7d,
            )
        )
        or 0
    )

    # 按动作聚合 (Top 10)
    by_action_rows = (
        await session.execute(
            select(
                AuditEvent.action,
                func.count(AuditEvent.event_id).label("cnt"),
            )
            .where(AuditEvent.tenant_id == tenant_uuid)
            .group_by(AuditEvent.action)
            .order_by(func.count(AuditEvent.event_id).desc())
            .limit(10)
        )
    ).all()
    by_action = [{"action": a, "count": int(c)} for a, c in by_action_rows]

    # 按用户聚合 (Top 10)
    by_user_rows = (
        await session.execute(
            select(
                AuditEvent.user_id,
                User.email,
                func.count(AuditEvent.event_id).label("cnt"),
            )
            .where(
                AuditEvent.tenant_id == tenant_uuid,
                AuditEvent.user_id.is_not(None),
            )
            .outerjoin(User, User.user_id == AuditEvent.user_id)
            .group_by(AuditEvent.user_id, User.email)
            .order_by(func.count(AuditEvent.event_id).desc())
            .limit(10)
        )
    ).all()
    by_user = [
        {"user_id": str(uid) if uid else None, "email": email or "", "count": int(c)} for uid, email, c in by_user_rows
    ]

    return AuditStats(
        total_events=int(total_events),
        unique_users=int(unique_users),
        unique_actions=int(unique_actions),
        last_24h_events=int(last_24h_events),
        last_7d_events=int(last_7d_events),
        by_action=by_action,
        by_user=by_user,
    )


@router.get(
    "/export",
    summary="审计事件 CSV 导出",
    description="流式导出 CSV (UTF-8 BOM, Excel 直接打开). 按时间区间过滤.",
)
async def export_audit_events(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    since: datetime | None = Query(default=None, description="起始时间"),
    until: datetime | None = Query(default=None, description="截止时间"),
) -> StreamingResponse:
    tenant_uuid = UUID(tenant_id)
    filename = f"audit_events_{tenant_uuid}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    async def stream():
        async for chunk in audit_service.iter_events_csv(session, tenant_uuid, since=since, until=until):
            yield chunk

    return StreamingResponse(
        stream(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


__all__ = ["router"]
