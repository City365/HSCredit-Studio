"""监控 / 运营 Dashboard API.

端点清单:

- ``GET /monitor/overview`` — 租户全局 KPI (Run/Node/Artifact/Workflow 数 + 24h 趋势)
- ``GET /monitor/runs/timeseries`` — Run 状态时间序列 (按小时聚合, 用于趋势图)
- ``GET /monitor/top-failures`` — Top 失败原因聚合 (按错误码分组)
- ``GET /monitor/nodes/throughput`` — 节点吞吐 (按节点类型统计 avg/p95 耗时)
- ``GET /monitor/alerts`` — 当前未解决告警 (KPI 阈值违规)

Phase 2 批次 11 实现 — 用于前端 ``/monitor`` 页面.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import case, func, select

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep
from hscredit_studio.models import (
    AuditEvent,
    NodeExecution,
    NodeArtifact,
    Run,
    Workflow,
    WorkflowVersion,
)
from hscredit_studio.core.logging import get_logger

router = APIRouter(tags=["监控"])
_log = get_logger(__name__)


# ===== Overview =====


@router.get(
    "/overview",
    summary="监控总览 KPI",
    description="返回租户全局 KPI: Run / Node / Artifact / Workflow 数 + 24h 趋势",
)
async def monitor_overview(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
) -> dict[str, Any]:
    tenant_uuid = UUID(tenant_id)
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    # Run 总数 / 活跃 / 24h / 7d
    run_total = await session.scalar(
        select(func.count(Run.run_id)).where(Run.tenant_id == tenant_uuid)
    ) or 0

    run_active = await session.scalar(
        select(func.count(Run.run_id)).where(
            Run.tenant_id == tenant_uuid,
            Run.status.in_(["running", "queued", "pending"]),
        )
    ) or 0

    run_24h = await session.scalar(
        select(func.count(Run.run_id)).where(
            Run.tenant_id == tenant_uuid,
            Run.submitted_at >= last_24h,
        )
    ) or 0

    run_7d = await session.scalar(
        select(func.count(Run.run_id)).where(
            Run.tenant_id == tenant_uuid,
            Run.submitted_at >= last_7d,
        )
    ) or 0

    run_success_24h = await session.scalar(
        select(func.count(Run.run_id)).where(
            Run.tenant_id == tenant_uuid,
            Run.submitted_at >= last_24h,
            Run.status == "success",
        )
    ) or 0

    run_failed_24h = await session.scalar(
        select(func.count(Run.run_id)).where(
            Run.tenant_id == tenant_uuid,
            Run.submitted_at >= last_24h,
            Run.status == "failed",
        )
    ) or 0

    success_rate = (run_success_24h / run_24h) if run_24h > 0 else 0.0

    # NodeExecution 总数 + 成功率
    node_total = await session.scalar(
        select(func.count(NodeExecution.node_exec_id)).where(
            NodeExecution.run_id.in_(
                select(Run.run_id).where(Run.tenant_id == tenant_uuid)
            )
        )
    ) or 0

    node_success = await session.scalar(
        select(func.count(NodeExecution.node_exec_id)).where(
            NodeExecution.status == "success",
            NodeExecution.run_id.in_(
                select(Run.run_id).where(Run.tenant_id == tenant_uuid)
            ),
        )
    ) or 0

    node_success_rate = (node_success / node_total) if node_total > 0 else 0.0

    # Workflow / Template
    wf_total = await session.scalar(
        select(func.count(Workflow.workflow_id)).where(
            Workflow.tenant_id == tenant_uuid, Workflow.deleted_at.is_(None)
        )
    ) or 0

    wf_version_total = await session.scalar(
        select(func.count(WorkflowVersion.version_id))
        .join(Workflow, Workflow.workflow_id == WorkflowVersion.workflow_id)
        .where(Workflow.tenant_id == tenant_uuid)
    ) or 0

    # Artifact 总数 + 总大小
    artifact_total = await session.scalar(
        select(func.count(NodeArtifact.artifact_id)).where(
            NodeArtifact.tenant_id == tenant_uuid
        )
    ) or 0

    artifact_size = await session.scalar(
        select(func.coalesce(func.sum(NodeArtifact.size_bytes), 0)).where(
            NodeArtifact.tenant_id == tenant_uuid
        )
    ) or 0

    # 平均 Run 耗时 (秒)
    avg_duration = await session.scalar(
        select(func.avg(Run.duration_sec)).where(
            Run.tenant_id == tenant_uuid,
            Run.status == "success",
            Run.duration_sec.is_not(None),
        )
    )
    avg_duration_s = float(avg_duration) if avg_duration else 0.0

    return {
        "run_total": int(run_total),
        "run_active": int(run_active),
        "run_24h": int(run_24h),
        "run_7d": int(run_7d),
        "run_success_24h": int(run_success_24h),
        "run_failed_24h": int(run_failed_24h),
        "run_success_rate_24h": round(success_rate, 4),
        "node_total": int(node_total),
        "node_success_rate": round(node_success_rate, 4),
        "workflow_total": int(wf_total),
        "workflow_version_total": int(wf_version_total),
        "artifact_total": int(artifact_total),
        "artifact_size_bytes": int(artifact_size),
        "avg_run_duration_seconds": round(avg_duration_s, 2),
        "as_of": now.isoformat(),
    }


# ===== Time-series =====


@router.get(
    "/runs/timeseries",
    summary="Run 时间序列",
    description="返回最近 N 小时的 Run 提交/成功/失败数量 (按小时聚合)",
)
async def runs_timeseries(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    hours: int = Query(default=24, ge=1, le=168, description="统计最近小时数"),
) -> dict[str, Any]:
    tenant_uuid = UUID(tenant_id)
    now = datetime.utcnow()
    since = now - timedelta(hours=hours)

    # 按小时分桶 (date_trunc hour)
    rows = (
        await session.execute(
            select(
                func.date_trunc("hour", Run.submitted_at).label("bucket"),
                func.count(Run.run_id).label("total"),
                func.sum(case((Run.status == "success", 1), else_=0)).label("success"),
                func.sum(case((Run.status == "failed", 1), else_=0)).label("failed"),
            )
            .where(
                Run.tenant_id == tenant_uuid,
                Run.submitted_at >= since,
            )
            .group_by("bucket")
            .order_by("bucket")
        )
    ).all()

    buckets = []
    for bucket, total, success, failed in rows:
        buckets.append(
            {
                "timestamp": bucket.isoformat() if bucket else None,
                "total": int(total or 0),
                "success": int(success or 0),
                "failed": int(failed or 0),
            }
        )
    return {"hours": hours, "buckets": buckets, "as_of": now.isoformat()}


# ===== Top failures =====


@router.get(
    "/top-failures",
    summary="Top 失败原因",
    description="聚合最近 N 小时 Run 失败, 按错误码统计 (用于定位系统性问题)",
)
async def top_failures(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    tenant_uuid = UUID(tenant_id)
    since = datetime.utcnow() - timedelta(hours=hours)

    rows = (
        await session.execute(
            select(
                Run.error,
                func.count(Run.run_id).label("cnt"),
                func.max(Run.submitted_at).label("last_seen"),
            )
            .where(
                Run.tenant_id == tenant_uuid,
                Run.status == "failed",
                Run.submitted_at >= since,
            )
            .group_by(Run.error)
            .order_by(func.count(Run.run_id).desc())
            .limit(limit)
        )
    ).all()

    failures = []
    for error_payload, cnt, last_seen in rows:
        # 提取错误码
        code = "UNKNOWN"
        message = ""
        if isinstance(error_payload, dict):
            code = error_payload.get("code") or "UNKNOWN"
            message = error_payload.get("message") or ""
        failures.append(
            {
                "code": code,
                "message": message[:200] if message else "",
                "count": int(cnt),
                "last_seen": last_seen.isoformat() if last_seen else None,
            }
        )
    return {"hours": hours, "failures": failures}


# ===== Node throughput =====


@router.get(
    "/nodes/throughput",
    summary="节点吞吐与耗时",
    description="按节点类型统计: 累计调用次数 / 平均耗时 / p95 耗时 / 成功率",
)
async def nodes_throughput(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    hours: int = Query(default=24, ge=1, le=168),
) -> dict[str, Any]:
    tenant_uuid = UUID(tenant_id)
    since = datetime.utcnow() - timedelta(hours=hours)

    rows = (
        await session.execute(
            select(
                NodeExecution.node_type,
                func.count(NodeExecution.node_exec_id).label("cnt"),
                func.sum(case((NodeExecution.status == "success", 1), else_=0)).label(
                    "success_cnt"
                ),
                func.avg(NodeExecution.duration_sec).label("avg_dur"),
                func.max(NodeExecution.duration_sec).label("max_dur"),
            )
            .where(
                NodeExecution.run_id.in_(
                    select(Run.run_id).where(
                        Run.tenant_id == tenant_uuid,
                        Run.submitted_at >= since,
                    )
                )
            )
            .group_by(NodeExecution.node_type)
            .order_by(func.count(NodeExecution.node_exec_id).desc())
        )
    ).all()

    stats = []
    for node_type, cnt, success_cnt, avg_dur, max_dur in rows:
        # p95 计算 (从所有 duration_sec 中 percentile)
        durations = (
            await session.scalars(
                select(NodeExecution.duration_sec)
                .where(
                    NodeExecution.node_type == node_type,
                    NodeExecution.run_id.in_(
                        select(Run.run_id).where(
                            Run.tenant_id == tenant_uuid,
                            Run.submitted_at >= since,
                        )
                    ),
                    NodeExecution.duration_sec.is_not(None),
                )
                .order_by(NodeExecution.duration_sec)
            )
        ).all()
        n = len(durations)
        p95 = float(durations[int(0.95 * n)]) if n > 0 else 0.0

        success_rate = (success_cnt / cnt) if cnt > 0 else 0.0
        stats.append(
            {
                "node_type": node_type,
                "count": int(cnt),
                "success_count": int(success_cnt or 0),
                "success_rate": round(success_rate, 4),
                "avg_duration_seconds": round(float(avg_dur or 0), 2),
                "p95_duration_seconds": round(p95, 2),
                "max_duration_seconds": round(float(max_dur or 0), 2),
            }
        )

    return {"hours": hours, "nodes": stats}


# ===== Active alerts =====


@router.get(
    "/alerts",
    summary="活跃告警",
    description="基于 KPI 阈值检测的活跃告警列表 (Phase 2 简单实现 — 内存规则引擎)",
)
async def active_alerts(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
) -> dict[str, Any]:
    tenant_uuid = UUID(tenant_id)
    now = datetime.utcnow()
    last_1h = now - timedelta(hours=1)

    alerts: list[dict[str, Any]] = []

    # Alert 1: 24h 失败率 > 30%
    failed_24h = await session.scalar(
        select(func.count(Run.run_id)).where(
            Run.tenant_id == tenant_uuid,
            Run.submitted_at >= now - timedelta(hours=24),
            Run.status == "failed",
        )
    ) or 0
    total_24h = await session.scalar(
        select(func.count(Run.run_id)).where(
            Run.tenant_id == tenant_uuid,
            Run.submitted_at >= now - timedelta(hours=24),
        )
    ) or 0
    if total_24h > 0:
        fail_rate = failed_24h / total_24h
        if fail_rate > 0.3:
            alerts.append(
                {
                    "severity": "critical" if fail_rate > 0.5 else "warning",
                    "code": "HIGH_FAILURE_RATE_24H",
                    "message": f"过去 24h 失败率 {fail_rate:.1%} (阈值 30%)",
                    "metric_value": round(fail_rate, 4),
                    "threshold": 0.3,
                    "as_of": now.isoformat(),
                }
            )

    # Alert 2: 平均 Run 耗时 > 5 分钟
    avg_dur = await session.scalar(
        select(func.avg(Run.duration_sec)).where(
            Run.tenant_id == tenant_uuid,
            Run.status == "success",
            Run.submitted_at >= now - timedelta(hours=24),
            Run.duration_sec.is_not(None),
        )
    )
    if avg_dur and float(avg_dur) > 300:
        alerts.append(
            {
                "severity": "warning",
                "code": "SLOW_RUN_DURATION_24H",
                "message": f"过去 24h 平均 Run 耗时 {float(avg_dur):.0f}s (阈值 300s)",
                "metric_value": round(float(avg_dur), 2),
                "threshold": 300,
                "as_of": now.isoformat(),
            }
        )

    # Alert 3: 最近 1h 失败 >= 5 次
    failed_1h = await session.scalar(
        select(func.count(Run.run_id)).where(
            Run.tenant_id == tenant_uuid,
            Run.submitted_at >= last_1h,
            Run.status == "failed",
        )
    ) or 0
    if failed_1h >= 5:
        alerts.append(
            {
                "severity": "critical" if failed_1h >= 10 else "warning",
                "code": "HIGH_FAILURE_COUNT_1H",
                "message": f"最近 1h 失败 {failed_1h} 次 (阈值 5 次)",
                "metric_value": int(failed_1h),
                "threshold": 5,
                "as_of": now.isoformat(),
            }
        )

    return {"alert_count": len(alerts), "alerts": alerts, "as_of": now.isoformat()}


__all__ = ["router"]