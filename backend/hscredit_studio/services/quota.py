"""订阅计划配置 — Phase 4 B19.

依据 docs/ROADMAP.md Phase 4 B19:

> 在 Tenant.plan 已有字段基础上加配置 (限额/超额处理),
> middleware 检查用量超 80% 触发预警, 超 100% 返回 402 Payment Required。

各 plan 月度配额 (默认; 可通过环境变量覆盖):

===================  ====================  ====================
free (default)       pro                  enterprise
===================  ====================  ====================
10 runs              200 runs              unlimited
30 min sandbox       10 hours sandbox     unlimited
1 GB storage         50 GB storage        unlimited
===================  ====================  ====================

配额检查逻辑 (Phase 4 B19 简化版):

- monthly_runs / monthly_duration_ms / monthly_storage_gb 三维度
- 超过 80% 触发 E_QUOTA_NEAR_LIMIT (warning)
- 超过 100% 触发 E_QUOTA_EXCEEDED (block)
- monthly_duration_ms 由 NodeResourceUsage 求和 (Phase 3 B17 数据)
- monthly_storage_gb 由 NodeArtifact 求和
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from hscredit_studio.core.database import session_scope
from hscredit_studio.core.logging import get_logger
from hscredit_studio.models import NodeArtifact, NodeResourceUsage, Run

_log = get_logger(__name__)


@dataclass
class PlanQuota:
    """单个 plan 的配额定义."""

    plan: str
    monthly_runs: int  # 0 表示不限
    monthly_duration_ms: int  # 0 表示不限
    monthly_storage_gb: float  # 0 表示不限

    def is_unlimited_runs(self) -> bool:
        return self.monthly_runs == 0

    def is_unlimited_duration(self) -> bool:
        return self.monthly_duration_ms == 0

    def is_unlimited_storage(self) -> bool:
        return self.monthly_storage_gb == 0


# ===== 默认配额映射 =====

_PLAN_QUOTAS: dict[str, PlanQuota] = {
    "free": PlanQuota(
        plan="free",
        monthly_runs=10,
        monthly_duration_ms=30 * 60 * 1000,  # 30 分钟
        monthly_storage_gb=1.0,
    ),
    "pro": PlanQuota(
        plan="pro",
        monthly_runs=200,
        monthly_duration_ms=10 * 60 * 60 * 1000,  # 10 小时
        monthly_storage_gb=50.0,
    ),
    "enterprise": PlanQuota(
        plan="enterprise",
        monthly_runs=0,  # unlimited
        monthly_duration_ms=0,
        monthly_storage_gb=0.0,
    ),
}


def get_plan_quota(plan: str) -> PlanQuota:
    """根据 plan 名取配额, 未知 plan 走 free 兜底."""
    return _PLAN_QUOTAS.get(plan, _PLAN_QUOTAS["free"])


# ===== 用量查询 / 配额检查 =====


@dataclass
class QuotaUsageSnapshot:
    """租户本月用量快照 (Phase 4 B19 验收)."""

    plan: str
    monthly_runs_used: int
    monthly_duration_ms_used: int
    monthly_storage_bytes_used: int
    monthly_runs_limit: int
    monthly_duration_ms_limit: int
    monthly_storage_gb_limit: float

    @property
    def monthly_storage_gb_used(self) -> float:
        return self.monthly_storage_bytes_used / (1024 ** 3)

    def usage_ratio(self, dim: str) -> float | None:
        """返回某维度的用量比例 (0.0 - 1.0+); unlimited 返回 None."""
        if dim == "runs":
            if self.monthly_runs_limit == 0:
                return None
            return self.monthly_runs_used / self.monthly_runs_limit
        if dim == "duration":
            if self.monthly_duration_ms_limit == 0:
                return None
            return self.monthly_duration_ms_used / self.monthly_duration_ms_limit
        if dim == "storage":
            if self.monthly_storage_gb_limit == 0:
                return None
            return self.monthly_storage_gb_used / self.monthly_storage_gb_limit
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan,
            "monthly_runs": {
                "used": self.monthly_runs_used,
                "limit": self.monthly_runs_limit,
                "unlimited": self.monthly_runs_limit == 0,
                "ratio": self.usage_ratio("runs"),
            },
            "monthly_duration_ms": {
                "used": self.monthly_duration_ms_used,
                "limit": self.monthly_duration_ms_limit,
                "unlimited": self.monthly_duration_ms_limit == 0,
                "ratio": self.usage_ratio("duration"),
            },
            "monthly_storage_gb": {
                "used": round(self.monthly_storage_gb_used, 4),
                "limit": self.monthly_storage_gb_limit,
                "unlimited": self.monthly_storage_gb_limit == 0,
                "ratio": self.usage_ratio("storage"),
            },
        }


async def get_quota_usage(tenant_id: UUID, plan: str) -> QuotaUsageSnapshot:
    """查询租户当前用量快照 (Phase 4 B19).

    Args:
        tenant_id: 租户 UUID.
        plan: 租户 plan (free / pro / enterprise).

    Returns:
        含本月 runs 数 / sandbox 总耗时 / storage 总字节 的快照.
    """
    quota = get_plan_quota(plan)
    from datetime import datetime

    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)

    async with session_scope() as session:
        # Run 数
        runs_used = await session.scalar(
            select(func.count(Run.run_id)).where(
                Run.tenant_id == tenant_id,
                Run.submitted_at >= month_start,
            )
        ) or 0

        # Sandbox 总耗时
        duration_used = await session.scalar(
            select(func.coalesce(func.sum(NodeResourceUsage.duration_ms), 0)).where(
                NodeResourceUsage.tenant_id == tenant_id,
                NodeResourceUsage.captured_at >= month_start,
            )
        ) or 0

        # Storage 总字节
        storage_used = await session.scalar(
            select(func.coalesce(func.sum(NodeArtifact.size_bytes), 0)).where(
                NodeArtifact.tenant_id == tenant_id,
                NodeArtifact.created_at >= month_start,
            )
        ) or 0

    return QuotaUsageSnapshot(
        plan=plan,
        monthly_runs_used=int(runs_used),
        monthly_duration_ms_used=int(duration_used),
        monthly_storage_bytes_used=int(storage_used),
        monthly_runs_limit=quota.monthly_runs,
        monthly_duration_ms_limit=quota.monthly_duration_ms,
        monthly_storage_gb_limit=quota.monthly_storage_gb,
    )


# ===== 配额检查 (Phase 4 B19 验收) =====


@dataclass
class QuotaCheckResult:
    """配额检查结果 (Phase 4 B19)."""

    allowed: bool
    near_limit: bool  # 任何维度 >= 80%
    exceeded_dim: str | None  # 超额维度 (None = 未超额)
    message: str


async def check_quota(
    tenant_id: UUID,
    plan: str,
    *,
    warn_threshold: float = 0.8,
) -> QuotaCheckResult:
    """检查租户是否超额 (Phase 4 B19 验收).

    Returns:
        :class:`QuotaCheckResult`, 含 allowed / near_limit / exceeded_dim / message.

    用法:
    - 在 Run 提交时调用, 决定是否允许.
    - 在 middleware / 前端轮询调用, 触发 80% 预警.
    """
    snapshot = await get_quota_usage(tenant_id, plan)
    near_limit = False
    exceeded_dim: str | None = None
    messages: list[str] = []

    for dim, label in [
        ("runs", "Run"),
        ("duration", "Sandbox 时长"),
        ("storage", "存储"),
    ]:
        ratio = snapshot.usage_ratio(dim)
        if ratio is None:
            # unlimited
            continue
        if ratio >= 1.0:
            exceeded_dim = dim
            messages.append(f"{label} 已超额 (用量 {ratio:.1%})")
        elif ratio >= warn_threshold:
            near_limit = True
            messages.append(f"{label} 接近限额 ({ratio:.1%})")

    if exceeded_dim:
        return QuotaCheckResult(
            allowed=False,
            near_limit=near_limit,
            exceeded_dim=exceeded_dim,
            message="; ".join(messages) + "。请升级订阅或清理资源。",
        )

    return QuotaCheckResult(
        allowed=True,
        near_limit=near_limit,
        exceeded_dim=None,
        message=("; ".join(messages) if messages else "用量正常"),
    )


__all__ = [
    "PlanQuota",
    "QuotaCheckResult",
    "QuotaUsageSnapshot",
    "check_quota",
    "get_plan_quota",
    "get_quota_usage",
]
