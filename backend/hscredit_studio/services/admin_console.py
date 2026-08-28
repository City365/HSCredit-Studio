"""租户超管后台 — Phase 6 B29.

依据 docs/ROADMAP.md Phase 6 B29:

> 仅 super_admin 可见 /admin 入口
> 跨租户仪表板: 租户列表、用量排行、健康度
> 租户详情: 用户、订阅、用量趋势、审计事件
> 租户启用/停用、迁移到其他集群

依赖: B28 (super_admin 角色) + B19 (用量基础).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select

from hscredit_studio.core.database import session_scope
from hscredit_studio.models import (
    AuditEvent,
    NodeResourceUsage,
    Tenant,
    TenantMember,
    User,
    UserRoleAudit,
)

# ===== 数据结构 =====


@dataclass
class TenantOverview:
    """单个租户的概览数据 (B29 跨租户仪表板)."""

    tenant_id: str
    slug: str
    name: str
    plan: str
    status: str
    member_count: int
    total_runs_30d: int
    total_cpu_seconds_30d: float
    last_active_at: datetime | None
    is_healthy: bool  # 简化: 最近 7 天有 run 即健康


@dataclass
class GlobalOverview:
    """全平台跨租户概览 (B29 仪表板顶层)."""

    total_tenants: int
    active_tenants: int
    suspended_tenants: int
    archived_tenants: int
    total_members: int
    total_runs_30d: int
    total_cpu_seconds_30d: float
    top_tenants_by_runs: list[TenantOverview]
    plan_distribution: dict[str, int]
    generated_at: datetime


# ===== 全平台概览 =====


async def get_global_overview() -> GlobalOverview:
    """返回全平台跨租户概览 (B29 仪表板)."""
    now = datetime.now(UTC)
    since_30d = (now - timedelta(days=30)).replace(tzinfo=None)

    async with session_scope() as session:
        # 租户聚合
        tenant_rows = await session.execute(
            select(
                func.count(Tenant.tenant_id).label("total"),
                func.sum(case((Tenant.status == "active", 1), else_=0)).label("active"),
                func.sum(case((Tenant.status == "suspended", 1), else_=0)).label("suspended"),
                func.sum(case((Tenant.status == "archived", 1), else_=0)).label("archived"),
            ).where(Tenant.deleted_at.is_(None))
        )
        t_row = tenant_rows.one()

        # 成员数
        member_row = await session.execute(
            select(func.count(TenantMember.user_id)).where(TenantMember.status == "active")
        )
        total_members = int(member_row.scalar() or 0)

        # 30 天用量汇总 (跨租户)
        usage_row = await session.execute(
            select(
                func.count(NodeResourceUsage.usage_id).label("total_runs"),
                func.coalesce(func.sum(NodeResourceUsage.cpu_seconds), 0).label("total_cpu"),
            ).where(NodeResourceUsage.captured_at >= since_30d)
        )
        u_row = usage_row.one()

        # Plan 分布
        plan_rows = await session.execute(
            select(Tenant.plan, func.count(Tenant.tenant_id))
            .where(Tenant.deleted_at.is_(None))
            .group_by(Tenant.plan)
        )
        plan_dist = {plan: int(count) for plan, count in plan_rows.all()}

    top_tenants = await get_top_tenants_by_runs(limit=10, days=30)

    return GlobalOverview(
        total_tenants=int(t_row.total or 0),
        active_tenants=int(t_row.active or 0),
        suspended_tenants=int(t_row.suspended or 0),
        archived_tenants=int(t_row.archived or 0),
        total_members=total_members,
        total_runs_30d=int(u_row.total_runs or 0),
        total_cpu_seconds_30d=float(u_row.total_cpu or 0),
        top_tenants_by_runs=top_tenants,
        plan_distribution=plan_dist,
        generated_at=now,
    )


async def get_top_tenants_by_runs(limit: int = 10, days: int = 30) -> list[TenantOverview]:
    """返回 30 天 Run 数 Top N 租户 (B29 用量排行)."""
    since_ts = (datetime.now(UTC) - timedelta(days=days)).replace(tzinfo=None)
    async with session_scope() as session:
        # 每个租户的 30 天 Run 数
        rows = await session.execute(
            select(
                Tenant.tenant_id,
                Tenant.slug,
                Tenant.name,
                Tenant.plan,
                Tenant.status,
                func.count(NodeResourceUsage.usage_id).label("runs"),
                func.coalesce(func.sum(NodeResourceUsage.cpu_seconds), 0).label("cpu"),
                func.max(NodeResourceUsage.captured_at).label("last_active"),
            )
            .outerjoin(
                NodeResourceUsage,
                (NodeResourceUsage.tenant_id == Tenant.tenant_id)
                & (NodeResourceUsage.captured_at >= since_ts),
            )
            .where(Tenant.deleted_at.is_(None))
            .group_by(
                Tenant.tenant_id,
                Tenant.slug,
                Tenant.name,
                Tenant.plan,
                Tenant.status,
            )
            .order_by(func.count(NodeResourceUsage.usage_id).desc())
            .limit(limit)
        )

        results: list[TenantOverview] = []
        for r in rows.all():
            tid = r.tenant_id
            member_count = await session.execute(
                select(func.count(TenantMember.user_id)).where(
                    TenantMember.tenant_id == tid,
                    TenantMember.status == "active",
                )
            )
            mc = int(member_count.scalar() or 0)
            last_active = r.last_active
            is_healthy = (
                last_active is not None
                and last_active.replace(tzinfo=None) >= (
                    datetime.now(UTC) - timedelta(days=7)
                ).replace(tzinfo=None)
            )
            results.append(
                TenantOverview(
                    tenant_id=str(tid),
                    slug=r.slug,
                    name=r.name,
                    plan=r.plan,
                    status=r.status,
                    member_count=mc,
                    total_runs_30d=int(r.runs or 0),
                    total_cpu_seconds_30d=float(r.cpu or 0),
                    last_active_at=last_active,
                    is_healthy=is_healthy,
                )
            )
        return results


# ===== 租户列表 =====


async def list_tenants(
    *,
    search: str | None = None,
    status_filter: str | None = None,
    plan_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """分页列出所有租户 (B29 跨租户仪表板).

    Returns:
        {items: [...], total: N, page: P, page_size: S}
    """
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    offset = (page - 1) * page_size

    async with session_scope() as session:
        stmt = select(Tenant).where(Tenant.deleted_at.is_(None))
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(func.lower(Tenant.name).like(like) | func.lower(Tenant.slug).like(like))
        if status_filter:
            stmt = stmt.where(Tenant.status == status_filter)
        if plan_filter:
            stmt = stmt.where(Tenant.plan == plan_filter)

        total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0

        rows = (
            await session.execute(
                stmt.order_by(Tenant.created_at.desc()).offset(offset).limit(page_size)
            )
        ).scalars().all()

        items = [
            {
                "tenant_id": str(t.tenant_id),
                "slug": t.slug,
                "name": t.name,
                "plan": t.plan,
                "status": t.status,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in rows
        ]

        return {
            "items": items,
            "total": int(total),
            "page": page,
            "page_size": page_size,
        }


# ===== 租户详情 =====


async def get_tenant_detail(tenant_id: UUID) -> dict[str, Any]:
    """返回单个租户的完整详情 (B29).

    包含: 基本信息 / members / 用量 / 30 天趋势 / 最近审计事件.
    """
    since_30d = (datetime.now(UTC) - timedelta(days=30)).replace(tzinfo=None)

    async with session_scope() as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None or tenant.deleted_at is not None:
            raise ValueError(f"租户 {tenant_id} 不存在或已删除")

        # 成员
        member_rows = await session.execute(
            select(TenantMember, User)
            .join(User, User.user_id == TenantMember.user_id)
            .where(TenantMember.tenant_id == tenant_id)
        )
        members = [
            {
                "user_id": str(m.user_id),
                "email": u.email,
                "display_name": u.display_name,
                "role": m.role,
                "status": m.status,
                "joined_at": m.joined_at,
            }
            for m, u in member_rows.all()
        ]

        # 用量 (30 天)
        usage_row = await session.execute(
            select(
                func.count(NodeResourceUsage.usage_id).label("runs"),
                func.coalesce(func.sum(NodeResourceUsage.cpu_seconds), 0).label("cpu"),
                func.coalesce(func.sum(NodeResourceUsage.duration_ms), 0).label("duration_ms"),
                func.coalesce(func.max(NodeResourceUsage.mem_peak_mb), 0).label("max_mem"),
            ).where(
                NodeResourceUsage.tenant_id == tenant_id,
                NodeResourceUsage.captured_at >= since_30d,
            )
        )
        u = usage_row.one()

        # 30 天趋势 (按天聚合 Run 数)
        trend_rows = await session.execute(
            select(
                func.date(NodeResourceUsage.captured_at).label("day"),
                func.count(NodeResourceUsage.usage_id).label("runs"),
            )
            .where(
                NodeResourceUsage.tenant_id == tenant_id,
                NodeResourceUsage.captured_at >= since_30d,
            )
            .group_by(func.date(NodeResourceUsage.captured_at))
            .order_by(func.date(NodeResourceUsage.captured_at))
        )
        trend = [
            {"date": str(day), "runs": int(runs)}
            for day, runs in trend_rows.all()
        ]

        # 最近审计事件
        audit_rows = await session.execute(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant_id)
            .order_by(AuditEvent.occurred_at.desc())
            .limit(20)
        )
        audit_events = [
            {
                "event_id": str(ev.event_id),
                "action": ev.action,
                "user_id": str(ev.user_id) if ev.user_id else None,
                "resource_type": ev.resource_type,
                "resource_id": ev.resource_id,
                "occurred_at": ev.occurred_at,
            }
            for ev in audit_rows.scalars().all()
        ]

        return {
            "tenant_id": str(tenant.tenant_id),
            "slug": tenant.slug,
            "name": tenant.name,
            "plan": tenant.plan,
            "status": tenant.status,
            "settings": tenant.settings,
            "created_at": tenant.created_at,
            "updated_at": tenant.updated_at,
            "members": members,
            "usage_30d": {
                "total_runs": int(u.runs or 0),
                "total_cpu_seconds": float(u.cpu or 0),
                "total_duration_ms": int(u.duration_ms or 0),
                "max_mem_peak_mb": float(u.max_mem or 0),
            },
            "usage_trend_30d": trend,
            "recent_audit_events": audit_events,
        }


# ===== 租户状态管理 =====


async def set_tenant_status(tenant_id: UUID, new_status: str) -> Tenant:
    """设置租户状态 (B29 启用/停用)."""
    if new_status not in ("active", "suspended", "archived"):
        raise ValueError(f"非法状态: {new_status}")
    async with session_scope() as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None or tenant.deleted_at is not None:
            raise ValueError(f"租户 {tenant_id} 不存在")
        tenant.status = new_status
        await session.commit()
        await session.refresh(tenant)
        return tenant


async def migrate_tenant(tenant_id: UUID, target_cluster: str) -> Tenant:
    """迁移租户到目标集群 (B29).

    当前实现: 将集群标签写入 ``Tenant.settings['cluster']``. 真正的集群迁移
    由运维脚本执行 (B29 留出 hooks, 此 API 仅记录元数据).
    """
    if not target_cluster or len(target_cluster) > 64:
        raise ValueError("目标集群标签不合法")
    async with session_scope() as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None or tenant.deleted_at is not None:
            raise ValueError(f"租户 {tenant_id} 不存在")
        settings = dict(tenant.settings or {})
        settings["cluster"] = target_cluster
        settings["migrated_at"] = datetime.now(UTC).isoformat()
        tenant.settings = settings
        await session.commit()
        await session.refresh(tenant)
        return tenant


# ===== 角色变更 (跨租户) =====


async def change_user_role(
    tenant_id: UUID,
    user_id: UUID,
    new_role: str,
    changed_by: UUID,
    reason: str | None = None,
) -> TenantMember:
    """变更用户在某租户的角色并写入审计 (B29 + B28 联动)."""
    if new_role not in ("owner", "admin", "analyst", "viewer"):
        raise ValueError(f"非法角色: {new_role}")
    async with session_scope() as session:
        member = await session.get(TenantMember, (tenant_id, user_id))
        if member is None:
            raise ValueError(f"成员不存在: tenant={tenant_id} user={user_id}")
        old_role = member.role
        member.role = new_role
        await session.flush()

        # 写审计 (PIPL 留痕)
        audit = UserRoleAudit(
            tenant_id=tenant_id,
            user_id=user_id,
            old_role=old_role,
            new_role=new_role,
            changed_by=changed_by,
            reason=reason,
        )
        session.add(audit)
        await session.commit()
        await session.refresh(member)
        return member


__all__ = [
    "GlobalOverview",
    "TenantOverview",
    "change_user_role",
    "get_global_overview",
    "get_tenant_detail",
    "get_top_tenants_by_runs",
    "list_tenants",
    "migrate_tenant",
    "set_tenant_status",
]
