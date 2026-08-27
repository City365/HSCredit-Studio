"""用量查询 API — Phase 4 B18.

依据 docs/ROADMAP.md Phase 4 B18:

> 提供 GET /api/v1/{tenant}/usage?from=&to= API, 按 Run / Sandbox / Storage / API Call 分维度返回。

数据源 (Phase 3 B17 + 现存表):
- Run 数 + 状态分布 — ``Run`` 表
- NodeResourceUsage 数 + 耗时 — ``NodeResourceUsage`` 表 (B17 采集)
- Artifact 数 + 大小 — ``NodeArtifact`` 表
- Workflow 数 — ``Workflow`` 表

注: API call 计数本 platform 当前未采集 (Phase 7 引入), 暂返回 0。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import case, func, select

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep
from hscredit_studio.models import NodeArtifact, Run, Workflow
from hscredit_studio.schemas.usage import (
    DimensionUsage,
    TenantUsageResponse,
)
from hscredit_studio.services.resource_usage import aggregate_by_tenant

router = APIRouter(tags=["用量"])


@router.get(
    "",
    summary="租户用量查询",
    description="返回租户在指定时间范围内的多维度用量 (Run/Sandbox/Storage/Workflow)",
    response_model=TenantUsageResponse,
)
async def get_tenant_usage(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    days: int = Query(default=30, ge=1, le=365, description="统计最近天数"),
    from_date: datetime | None = Query(default=None, description="起始时间 (ISO 8601)"),
    to_date: datetime | None = Query(default=None, description="截止时间 (ISO 8601)"),
) -> TenantUsageResponse:
    """Phase 4 B18 — 租户用量查询.

    维度:
    - ``runs``: Run 数 + 状态分布 + Sandbox 耗时
    - ``artifacts``: 产物数 + 总大小
    - ``workflows``: 工作流数 + 版本数
    - ``api_calls``: 0 (Phase 7 引入, 当前未采集)
    """
    tenant_uuid = UUID(tenant_id)
    now = datetime.utcnow()
    since = from_date or (now - timedelta(days=days))
    until = to_date or now

    # Run 维度
    run_row = await session.execute(
        select(
            func.count(Run.run_id).label("total"),
            func.sum(case((Run.status == "success", 1), else_=0)).label("success_cnt"),
            func.sum(case((Run.status == "failed", 1), else_=0)).label("failed_cnt"),
            func.sum(case((Run.status.in_(["running", "queued", "pending"]), 1), else_=0)).label(
                "active_cnt"
            ),
        ).where(
            Run.tenant_id == tenant_uuid,
            Run.submitted_at >= since,
            Run.submitted_at <= until,
        )
    )
    run_data = run_row.one()

    # Sandbox 维度 (来自 B17 的 NodeResourceUsage)
    sandbox_data = await aggregate_by_tenant(tenant_uuid, days=days)

    # Artifact 维度
    artifact_row = await session.execute(
        select(
            func.count(NodeArtifact.artifact_id).label("total"),
            func.coalesce(func.sum(NodeArtifact.size_bytes), 0).label("total_bytes"),
        ).where(
            NodeArtifact.tenant_id == tenant_uuid,
            NodeArtifact.created_at >= since,
            NodeArtifact.created_at <= until,
        )
    )
    artifact_data = artifact_row.one()

    # Workflow 维度
    workflow_row = await session.execute(
        select(
            func.count(Workflow.workflow_id).label("total"),
        ).where(
            Workflow.tenant_id == tenant_uuid,
            Workflow.deleted_at.is_(None),
            Workflow.created_at <= until,
        )
    )
    workflow_data = workflow_row.one()

    # API call 维度 (Phase 7 引入, 当前未采集)
    api_call_total = 0

    return TenantUsageResponse(
        tenant_id=tenant_uuid,
        range_start=since,
        range_end=until,
        runs=DimensionUsage(
            total=int(run_data.total or 0),
            success_count=int(run_data.success_cnt or 0),
            failed_count=int(run_data.failed_cnt or 0),
            active_count=int(run_data.active_cnt or 0),
        ),
        sandbox=DimensionUsage(
            total=sandbox_data["total_runs"],
            total_duration_ms=sandbox_data["total_duration_ms"],
            total_cpu_seconds=sandbox_data["total_cpu_seconds"],
            max_mem_peak_mb=sandbox_data["max_mem_peak_mb"],
            by_node_type=sandbox_data["by_node_type"],
        ),
        artifacts=DimensionUsage(
            total=int(artifact_data.total or 0),
            total_bytes=int(artifact_data.total_bytes or 0),
        ),
        workflows=DimensionUsage(
            total=int(workflow_data.total or 0),
        ),
        api_calls=DimensionUsage(total=api_call_total),
    )


__all__ = ["router"]
