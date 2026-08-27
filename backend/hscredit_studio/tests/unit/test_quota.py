"""Phase 4 B19 订阅计划与配额 — 单元测试.

依据 docs/ROADMAP.md Phase 4 B19:

- Plan 配额定义: free / pro / enterprise 三档
- QuotaUsageSnapshot: used / limit / ratio
- check_quota: allowed / near_limit / exceeded_dim

注: DB 集成测试在 E2E 中验证 (scripts/e2e/run_e2e_phase4_b19.py),
    这里只测纯 Python 逻辑。
"""
from __future__ import annotations

from hscredit_studio.services.quota import (
    QuotaCheckResult,
    QuotaUsageSnapshot,
    get_plan_quota,
)


def test_get_plan_quota_known_plans():
    """get_plan_quota: free/pro/enterprise 三档配置正确."""
    free = get_plan_quota("free")
    pro = get_plan_quota("pro")
    ent = get_plan_quota("enterprise")

    assert free.plan == "free"
    assert free.monthly_runs == 10
    assert free.monthly_duration_ms == 30 * 60 * 1000
    assert free.monthly_storage_gb == 1.0

    assert pro.plan == "pro"
    assert pro.monthly_runs == 200
    assert pro.monthly_duration_ms == 10 * 60 * 60 * 1000
    assert pro.monthly_storage_gb == 50.0

    assert ent.plan == "enterprise"
    assert ent.monthly_runs == 0  # unlimited
    assert ent.monthly_duration_ms == 0
    assert ent.monthly_storage_gb == 0.0


def test_get_plan_quota_unknown_falls_back_to_free():
    """get_plan_quota: 未知 plan 走 free 兜底."""
    assert get_plan_quota("unknown_plan").plan == "free"
    assert get_plan_quota("").plan == "free"


def test_plan_quota_unlimited_helpers():
    """PlanQuota: is_unlimited_* 辅助方法正确."""
    ent = get_plan_quota("enterprise")
    assert ent.is_unlimited_runs()
    assert ent.is_unlimited_duration()
    assert ent.is_unlimited_storage()

    free = get_plan_quota("free")
    assert not free.is_unlimited_runs()
    assert not free.is_unlimited_duration()
    assert not free.is_unlimited_storage()


def test_quota_usage_snapshot_ratio_calculation():
    """QuotaUsageSnapshot: usage_ratio 各维度计算正确."""
    snap = QuotaUsageSnapshot(
        plan="free",
        monthly_runs_used=8,  # 80% of 10
        monthly_duration_ms_used=15 * 60 * 1000,  # 50% of 30min
        monthly_storage_bytes_used=int(0.5 * (1024 ** 3)),  # 50% of 1GB
        monthly_runs_limit=10,
        monthly_duration_ms_limit=30 * 60 * 1000,
        monthly_storage_gb_limit=1.0,
    )
    assert abs(snap.usage_ratio("runs") - 0.8) < 1e-9
    assert abs(snap.usage_ratio("duration") - 0.5) < 1e-9
    assert abs(snap.usage_ratio("storage") - 0.5) < 1e-9
    assert snap.usage_ratio("unknown_dim") is None


def test_quota_usage_snapshot_unlimited_returns_none():
    """QuotaUsageSnapshot: unlimited 维度 ratio = None."""
    snap = QuotaUsageSnapshot(
        plan="enterprise",
        monthly_runs_used=99999,
        monthly_duration_ms_used=99999,
        monthly_storage_bytes_used=999999999,
        monthly_runs_limit=0,  # unlimited
        monthly_duration_ms_limit=0,
        monthly_storage_gb_limit=0.0,
    )
    assert snap.usage_ratio("runs") is None
    assert snap.usage_ratio("duration") is None
    assert snap.usage_ratio("storage") is None


def test_quota_usage_snapshot_to_dict():
    """QuotaUsageSnapshot.to_dict: 含 used/limit/unlimited/ratio."""
    snap = QuotaUsageSnapshot(
        plan="free",
        monthly_runs_used=5,
        monthly_duration_ms_used=10 * 60 * 1000,
        monthly_storage_bytes_used=int(0.5 * (1024 ** 3)),
        monthly_runs_limit=10,
        monthly_duration_ms_limit=30 * 60 * 1000,
        monthly_storage_gb_limit=1.0,
    )
    d = snap.to_dict()
    assert d["plan"] == "free"
    assert d["monthly_runs"]["used"] == 5
    assert d["monthly_runs"]["limit"] == 10
    assert d["monthly_runs"]["unlimited"] is False
    assert d["monthly_runs"]["ratio"] == 0.5
    assert d["monthly_duration_ms"]["unlimited"] is False
    assert d["monthly_storage_gb"]["unlimited"] is False


def test_quota_check_result_dataclass():
    """QuotaCheckResult: dataclass 字段."""
    r = QuotaCheckResult(
        allowed=True,
        near_limit=False,
        exceeded_dim=None,
        message="用量正常",
    )
    assert r.allowed is True
    assert r.near_limit is False
    assert r.exceeded_dim is None
    assert r.message == "用量正常"


def test_quota_check_result_exceeded():
    """QuotaCheckResult: 超额场景字段."""
    r = QuotaCheckResult(
        allowed=False,
        near_limit=True,
        exceeded_dim="runs",
        message="Run 已超额 (用量 105%)",
    )
    assert r.allowed is False
    assert r.near_limit is True
    assert r.exceeded_dim == "runs"
