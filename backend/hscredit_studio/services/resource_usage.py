"""节点沙箱资源用量落库服务 — Phase 3 B17.

依据 docs/ROADMAP.md Phase 3 B17:

> 每次沙箱 Job 记录 cpu_seconds / mem_peak_mb / duration_ms, 写入 NodeResourceUsage 表,
> 为 Phase 4 计费做数据准备。

设计:

- :func:`record_resource_usage` 同步调用 (在 :func:`_run_node_async` 末尾 commit 前插入)
- 写入失败时仅 WARN 日志, 不阻塞 Run 主流程 (资源采集不应让 Run 失败)
- :func:`aggregate_by_tenant` 供 Phase 4 / Phase 5 聚合查询
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from hscredit_studio.core.database import session_scope
from hscredit_studio.core.logging import get_logger
from hscredit_studio.models import NodeResourceUsage
from hscredit_studio.services.sandbox import SandboxResourceUsage

_log = get_logger(__name__)


async def record_resource_usage(
    *,
    node_exec_id: UUID,
    node_type: str,
    tenant_id: UUID | None,
    usage: SandboxResourceUsage,
    sandbox_backend: str = "subprocess",
) -> NodeResourceUsage | None:
    """记录单次沙箱执行的资源用量 (Phase 3 B17 验收).

    Args:
        node_exec_id: 关联 NodeExecution.
        node_type: 节点类型.
        tenant_id: 租户 ID (可空, anonymous 时).
        usage: 沙箱返回的 SandboxResourceUsage.
        sandbox_backend: 沙箱后端标识 (默认 subprocess).

    Returns:
        写入的 NodeResourceUsage 实例, 失败时返回 None (WARN 日志).
    """
    try:
        async with session_scope() as session:
            record = NodeResourceUsage(
                node_exec_id=node_exec_id,
                node_type=node_type,
                tenant_id=tenant_id,
                cpu_seconds=usage.cpu_seconds,
                mem_peak_mb=usage.mem_peak_mb,
                duration_ms=usage.duration_ms,
                sandbox_backend=sandbox_backend,
                status=usage.status,
                captured_at=datetime.utcnow(),
            )
            session.add(record)
            await session.commit()
            _log.info(
                "resource_usage_recorded",
                node_exec_id=str(node_exec_id),
                node_type=node_type,
                duration_ms=usage.duration_ms,
                cpu_seconds=round(usage.cpu_seconds, 3),
                mem_peak_mb=round(usage.mem_peak_mb, 1),
                status=usage.status,
            )
            return record
    except Exception as e:
        # 落库失败不应阻塞 Run 主流程
        _log.warning(
            "resource_usage_record_failed",
            node_exec_id=str(node_exec_id),
            node_type=node_type,
            error=str(e)[:200],
        )
        return None


async def aggregate_by_tenant(
    tenant_id: UUID,
    *,
    days: int = 30,
) -> dict[str, Any]:
    """聚合租户最近 N 天的资源用量 (供 Phase 4 计费 / Phase 5 监控).

    Returns:
        字典含 total_runs / total_cpu_seconds / total_duration_ms /
        total_mem_peak_mb / by_node_type (列表)。
    """
    since = datetime.utcnow() - timedelta(days=days)
    async with session_scope() as session:
        # 总计
        total_row = await session.execute(
            select(
                func.count(NodeResourceUsage.usage_id).label("total_runs"),
                func.coalesce(func.sum(NodeResourceUsage.cpu_seconds), 0).label("total_cpu"),
                func.coalesce(func.sum(NodeResourceUsage.duration_ms), 0).label("total_duration_ms"),
                func.coalesce(func.max(NodeResourceUsage.mem_peak_mb), 0).label("max_mem_mb"),
            ).where(
                NodeResourceUsage.tenant_id == tenant_id,
                NodeResourceUsage.captured_at >= since,
            )
        )
        row = total_row.one()

        # 按节点类型聚合
        by_node_type_rows = await session.execute(
            select(
                NodeResourceUsage.node_type,
                func.count(NodeResourceUsage.usage_id).label("runs"),
                func.coalesce(func.sum(NodeResourceUsage.duration_ms), 0).label("total_duration_ms"),
            )
            .where(
                NodeResourceUsage.tenant_id == tenant_id,
                NodeResourceUsage.captured_at >= since,
            )
            .group_by(NodeResourceUsage.node_type)
            .order_by(func.count(NodeResourceUsage.usage_id).desc())
        )
        by_node_type = [
            {"node_type": nt, "runs": int(runs), "total_duration_ms": int(dur_ms)}
            for nt, runs, dur_ms in by_node_type_rows.all()
        ]

    return {
        "tenant_id": str(tenant_id),
        "days": days,
        "total_runs": int(row.total_runs),
        "total_cpu_seconds": float(row.total_cpu),
        "total_duration_ms": int(row.total_duration_ms),
        "max_mem_peak_mb": float(row.max_mem_mb),
        "by_node_type": by_node_type,
    }


__all__ = ["aggregate_by_tenant", "record_resource_usage"]
