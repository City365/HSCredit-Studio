"""配额查询 API — Phase 4 B19.

依据 docs/ROADMAP.md Phase 4 B19:

> 提供 GET /api/v1/{tenant}/quota, 返回 plan 限额 + 已用 / 剩余。
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep
from hscredit_studio.models import Tenant
from hscredit_studio.services.quota import (
    check_quota,
    get_quota_usage,
)

router = APIRouter(tags=["配额"])


@router.get(
    "",
    summary="租户配额查询",
    description="返回租户当前用量与计划限额 (runs/duration/storage 三维度)",
)
async def get_tenant_quota(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    warn_threshold: float = Query(default=0.8, ge=0.0, le=1.0),
) -> dict:
    """Phase 4 B19 — 租户配额查询.

    Returns:
        字典含 plan + 各维度 used/limit/ratio + allowed/near_limit/exceeded_dim。
    """
    # 查 plan
    from uuid import UUID as _UUID

    tid = _UUID(tenant_id)
    plan = await session.scalar(select(Tenant.plan).where(Tenant.tenant_id == tid)) or "free"

    # 用量快照
    snapshot = await get_quota_usage(tid, plan)

    # 配额检查
    check = await check_quota(tid, plan, warn_threshold=warn_threshold)

    return {
        "snapshot": snapshot.to_dict(),
        "check": {
            "allowed": check.allowed,
            "near_limit": check.near_limit,
            "exceeded_dim": check.exceeded_dim,
            "message": check.message,
        },
    }


__all__ = ["router"]
