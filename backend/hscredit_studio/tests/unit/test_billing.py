"""Phase 4 B20 账单与发票 — 单元测试.

依据 docs/ROADMAP.md Phase 4 B20 验收:

- 账单计算: 基础订阅费 + 三维度超量费
- BillComputation dataclass 字段
- 发票号生成: INV-YYYY-MM-NNN 格式
- 支付链接 mock: 必填字段

注: DB 集成测试在 E2E 中验证 (scripts/e2e/run_e2e_phase4_b20.py)。
"""
from __future__ import annotations

import pytest

from hscredit_studio.services.billing import (
    BASE_FEE,
    OVERAGE_DURATION_HOUR_PRICE,
    OVERAGE_RUN_PRICE,
    OVERAGE_STORAGE_GB_PRICE,
    TAX_RATE,
    BillComputation,
    compute_bill,
    create_payment_link,
)


def _free_snapshot(runs: int, duration_ms: int, storage_bytes: int):
    """构造 free plan 用量快照 (10 runs / 30min / 1GB)."""
    from hscredit_studio.services.quota import QuotaUsageSnapshot

    return QuotaUsageSnapshot(
        plan="free",
        monthly_runs_used=runs,
        monthly_duration_ms_used=duration_ms,
        monthly_storage_bytes_used=storage_bytes,
        monthly_runs_limit=10,
        monthly_duration_ms_limit=30 * 60 * 1000,
        monthly_storage_gb_limit=1.0,
    )


def _pro_snapshot(runs: int, duration_ms: int, storage_bytes: int):
    """构造 pro plan 用量快照 (200 runs / 10h / 50GB)."""
    from hscredit_studio.services.quota import QuotaUsageSnapshot

    return QuotaUsageSnapshot(
        plan="pro",
        monthly_runs_used=runs,
        monthly_duration_ms_used=duration_ms,
        monthly_storage_bytes_used=storage_bytes,
        monthly_runs_limit=200,
        monthly_duration_ms_limit=10 * 60 * 60 * 1000,
        monthly_storage_gb_limit=50.0,
    )


def test_base_fee_per_plan():
    """BASE_FEE: free=0, pro=199, enterprise=0 (报价制)."""
    assert BASE_FEE["free"] == 0.0
    assert BASE_FEE["pro"] == 199.0
    assert BASE_FEE["enterprise"] == 0.0


def test_overage_prices_positive():
    """超量单价 > 0."""
    assert OVERAGE_RUN_PRICE > 0
    assert OVERAGE_DURATION_HOUR_PRICE > 0
    assert OVERAGE_STORAGE_GB_PRICE > 0


def test_tax_rate_reasonable():
    """TAX_RATE: 中国增值税 13%."""
    assert 0.05 <= TAX_RATE <= 0.20


def test_compute_bill_free_no_overage():
    """compute_bill: free plan 无超量, 总费用 = 0 (税前) + 0 (税)."""
    snap = _free_snapshot(runs=5, duration_ms=10 * 60 * 1000, storage_bytes=int(0.5 * 1024 ** 3))
    comp = compute_bill("free", "2026-08", snap)

    assert comp.plan == "free"
    assert comp.base_fee == 0.0
    assert comp.overage_runs == 0
    assert comp.overage_runs_fee == 0.0
    assert comp.overage_duration_ms == 0
    assert comp.overage_storage_bytes == 0
    assert comp.total_amount == 0.0
    assert comp.tax_amount == 0.0
    assert comp.grand_total == 0.0


def test_compute_bill_free_with_overage():
    """compute_bill: free plan 超量 (12 runs, 35min, 1.5GB)."""
    snap = _free_snapshot(
        runs=12,
        duration_ms=35 * 60 * 1000,
        storage_bytes=int(1.5 * 1024 ** 3),
    )
    comp = compute_bill("free", "2026-08", snap)

    assert comp.base_fee == 0.0
    # 12 - 10 = 2 超量 runs * 5 = 10
    assert comp.overage_runs == 2
    assert comp.overage_runs_fee == 10.0
    # (35 - 30) min = 5 min = 5/60 hour * 10 = 0.8333
    assert comp.overage_duration_ms == 5 * 60 * 1000
    assert abs(comp.overage_duration_fee - 0.8333) < 0.01
    # 0.5 GB * 2 = 1.0
    assert comp.overage_storage_bytes == int(0.5 * 1024 ** 3)
    assert abs(comp.overage_storage_fee - 1.0) < 0.01

    expected_subtotal = 10.0 + 0.8333 + 1.0
    expected_tax = expected_subtotal * TAX_RATE
    assert abs(comp.total_amount - expected_subtotal) < 0.01
    assert abs(comp.grand_total - (expected_subtotal + expected_tax)) < 0.01


def test_compute_bill_pro_no_overage():
    """compute_bill: pro plan 用量未超, 总费用 = 199 + 199*13%."""
    snap = _pro_snapshot(runs=50, duration_ms=2 * 60 * 60 * 1000, storage_bytes=(10 * 1024 ** 3))
    comp = compute_bill("pro", "2026-08", snap)

    assert comp.base_fee == 199.0
    assert comp.overage_runs == 0
    assert comp.overage_runs_fee == 0.0
    assert comp.overage_duration_ms == 0
    assert comp.overage_storage_bytes == 0
    assert comp.total_amount == 199.0
    assert abs(comp.tax_amount - 199.0 * TAX_RATE) < 0.01
    assert abs(comp.grand_total - 199.0 * (1 + TAX_RATE)) < 0.01


def test_compute_bill_enterprise_unlimited():
    """compute_bill: enterprise plan 全 unlimited, 总费用 = 0."""
    snap = _free_snapshot(runs=99999, duration_ms=99999 * 60 * 1000, storage_bytes=99999 * 1024 ** 3)
    comp = compute_bill("enterprise", "2026-08", snap)

    assert comp.base_fee == 0.0
    assert comp.overage_runs == 0
    assert comp.overage_runs_fee == 0.0
    assert comp.overage_duration_ms == 0
    assert comp.overage_storage_bytes == 0
    assert comp.total_amount == 0.0


def test_bill_computation_to_dict():
    """BillComputation.to_dict: 含所有字段."""
    comp = BillComputation(
        plan="pro",
        billing_period="2026-08",
        base_fee=199.0,
        overage_runs=10,
        overage_runs_fee=50.0,
        overage_duration_ms=60 * 60 * 1000,
        overage_duration_fee=10.0,
        overage_storage_bytes=(2 * 1024 ** 3),
        overage_storage_fee=4.0,
        total_amount=263.0,
        tax_amount=34.19,
        grand_total=297.19,
        currency="CNY",
    )
    d = comp.to_dict()
    assert d["plan"] == "pro"
    assert d["base_fee"] == 199.0
    assert d["overage_runs"] == 10
    assert d["total_amount"] == 263.0
    assert d["currency"] == "CNY"


@pytest.mark.asyncio
async def test_create_payment_link_wechat():
    """create_payment_link: 微信支付 mock URL."""
    from datetime import datetime

    from hscredit_studio.models.billing import Bill

    bill = Bill(
        bill_id="00000000-0000-0000-0000-000000000001",
        tenant_id="00000000-0000-0000-0000-000000000002",
        billing_period="2026-08",
        plan="pro",
        status="pending",
        base_fee=199.0,
        total_amount=224.87,
        currency="CNY",
        due_date=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    result = await create_payment_link(bill, channel="wechat")
    assert result["channel"] == "wechat"
    assert "payment_url" in result
    assert "wechat" in result["payment_url"]
    assert result["mock"] is True
    assert result["amount"] == 224.87


@pytest.mark.asyncio
async def test_create_payment_link_invalid_channel():
    """create_payment_link: 不支持的通道抛错."""
    from datetime import datetime

    from hscredit_studio.models.billing import Bill

    bill = Bill(
        bill_id="00000000-0000-0000-0000-000000000001",
        tenant_id="00000000-0000-0000-0000-000000000002",
        billing_period="2026-08",
        plan="pro",
        status="pending",
        base_fee=0.0,
        total_amount=0.0,
        currency="CNY",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    with pytest.raises(ValueError, match="不支持"):
        await create_payment_link(bill, channel="invalid_channel")
