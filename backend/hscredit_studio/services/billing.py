"""账单计算与发票生成 — Phase 4 B20.

依据 docs/ROADMAP.md Phase 4 B20:

> 月度账单生成 (cron + 异步任务)
> 集成 Stripe / 微信支付 / 支付宝
> PDF 发票生成 (中文模板)
> 财务对账导出

设计:

- :func:`compute_bill` — 计算某账期账单金额 (基础 + 三维度超量)
- :func:`generate_bill_for_tenant` — 写库生成 Bill 记录
- :func:`generate_invoice_pdf` — 生成中文 PDF 发票 (简化文本格式, 本地文件)
- :func:`export_reconciliation_csv` — 财务对账 CSV 导出

支付集成:
- Stripe: SDK 不在本地 dev, 留接口 + mock 成功响应
- 微信支付 / 支付宝: 同上
- 生产部署时配真实 webhook + 回调签名校验
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from hscredit_studio.core.database import session_scope
from hscredit_studio.core.logging import get_logger
from hscredit_studio.models import Bill, Invoice
from hscredit_studio.services.quota import (
    QuotaUsageSnapshot,
    get_plan_quota,
    get_quota_usage,
)

_log = get_logger(__name__)


# ===== 价格配置 (Phase 4 B20 修订) =====

# 基础订阅月费 (元)
BASE_FEE: dict[str, float] = {
    "free": 0.0,
    "pro": 199.0,
    "enterprise": 0.0,  # 报价制, 按合同
}

# 超量单价 (元/单位)
OVERAGE_RUN_PRICE = 5.0         # 每超 1 run
OVERAGE_DURATION_HOUR_PRICE = 10.0  # 每超 1 小时
OVERAGE_STORAGE_GB_PRICE = 2.0   # 每超 1 GB

# 税率 (中国增值税一般纳税人 13%)
TAX_RATE = 0.13


@dataclass
class BillComputation:
    """账单计算结果 (Phase 4 B20)."""

    plan: str
    billing_period: str
    base_fee: float
    overage_runs: int
    overage_runs_fee: float
    overage_duration_ms: int
    overage_duration_fee: float
    overage_storage_bytes: int
    overage_storage_fee: float
    total_amount: float
    tax_amount: float
    grand_total: float
    currency: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan,
            "billing_period": self.billing_period,
            "base_fee": self.base_fee,
            "overage_runs": self.overage_runs,
            "overage_runs_fee": round(self.overage_runs_fee, 2),
            "overage_duration_ms": self.overage_duration_ms,
            "overage_duration_fee": round(self.overage_duration_fee, 2),
            "overage_storage_bytes": self.overage_storage_bytes,
            "overage_storage_fee": round(self.overage_storage_fee, 2),
            "total_amount": round(self.total_amount, 2),
            "tax_amount": round(self.tax_amount, 2),
            "grand_total": round(self.grand_total, 2),
            "currency": self.currency,
        }


def compute_bill(plan: str, billing_period: str, snapshot: QuotaUsageSnapshot) -> BillComputation:
    """根据用量快照计算账单 (Phase 4 B20).

    Args:
        plan: 租户 plan.
        billing_period: 账期 YYYY-MM.
        snapshot: 配额用量快照.

    Returns:
        :class:`BillComputation` 含各项费用.
    """
    quota = get_plan_quota(plan)
    base_fee = BASE_FEE.get(plan, 0.0)

    # Run 超量
    if quota.monthly_runs == 0:
        overage_runs = 0
        overage_runs_fee = 0.0
    else:
        overage_runs = max(0, snapshot.monthly_runs_used - quota.monthly_runs)
        overage_runs_fee = overage_runs * OVERAGE_RUN_PRICE

    # Duration 超量 (ms → hour)
    if quota.monthly_duration_ms == 0:
        overage_duration_ms = 0
        overage_duration_fee = 0.0
    else:
        overage_duration_ms = max(0, snapshot.monthly_duration_ms_used - quota.monthly_duration_ms)
        overage_duration_hours = overage_duration_ms / (1000 * 3600)
        overage_duration_fee = overage_duration_hours * OVERAGE_DURATION_HOUR_PRICE

    # Storage 超量 (bytes → GB)
    if quota.monthly_storage_gb == 0.0:
        overage_storage_bytes = 0
        overage_storage_fee = 0.0
    else:
        overage_storage_bytes = max(
            0,
            snapshot.monthly_storage_bytes_used - int(quota.monthly_storage_gb * (1024 ** 3)),
        )
        overage_storage_gb = overage_storage_bytes / (1024 ** 3)
        overage_storage_fee = overage_storage_gb * OVERAGE_STORAGE_GB_PRICE

    total_amount = base_fee + overage_runs_fee + overage_duration_fee + overage_storage_fee
    tax_amount = total_amount * TAX_RATE
    grand_total = total_amount + tax_amount

    return BillComputation(
        plan=plan,
        billing_period=billing_period,
        base_fee=base_fee,
        overage_runs=overage_runs,
        overage_runs_fee=overage_runs_fee,
        overage_duration_ms=overage_duration_ms,
        overage_duration_fee=overage_duration_fee,
        overage_storage_bytes=overage_storage_bytes,
        overage_storage_fee=overage_storage_fee,
        total_amount=total_amount,
        tax_amount=tax_amount,
        grand_total=grand_total,
        currency="CNY",
    )


async def generate_bill_for_tenant(
    tenant_id: UUID,
    plan: str,
    billing_period: str,
    *,
    due_days: int = 30,
) -> Bill:
    """生成某租户某账期的账单并落库 (Phase 4 B20 验收).

    重复账期则返回已有账单 (幂等).

    Returns:
        新建或已存在的 :class:`Bill` 实例.
    """
    snapshot = await get_quota_usage(tenant_id, plan)
    comp = compute_bill(plan, billing_period, snapshot)

    now = datetime.utcnow()
    due_date = now + timedelta(days=due_days)

    async with session_scope() as session:
        # 检查是否已存在
        existing = await session.scalar(
            select(Bill).where(
                Bill.tenant_id == tenant_id,
                Bill.billing_period == billing_period,
            )
        )
        if existing:
            _log.info(
                "bill_already_exists",
                tenant_id=str(tenant_id),
                billing_period=billing_period,
                bill_id=str(existing.bill_id),
            )
            return existing

        bill = Bill(
            tenant_id=tenant_id,
            billing_period=billing_period,
            plan=plan,
            status="pending",
            base_fee=comp.base_fee,
            overage_runs_fee=comp.overage_runs_fee,
            overage_duration_fee=comp.overage_duration_fee,
            overage_storage_fee=comp.overage_storage_fee,
            total_amount=comp.grand_total,  # 含税总额
            currency=comp.currency,
            due_date=due_date,
            extra_metadata={
                "overage_runs": comp.overage_runs,
                "overage_duration_ms": comp.overage_duration_ms,
                "overage_storage_bytes": comp.overage_storage_bytes,
                "subtotal": comp.total_amount,
                "tax_amount": comp.tax_amount,
                "tax_rate": TAX_RATE,
            },
        )
        session.add(bill)
        await session.commit()
        await session.refresh(bill)
        _log.info(
            "bill_generated",
            bill_id=str(bill.bill_id),
            tenant_id=str(tenant_id),
            billing_period=billing_period,
            grand_total=comp.grand_total,
        )
        return bill


# ===== 发票 PDF 生成 =====


def generate_invoice_pdf(
    *,
    tenant_name: str,
    bill: Bill,
    output_path: str,
    invoice_number: str,
) -> str:
    """生成中文发票 PDF (Phase 4 B20).

    当前迭代: 生成简化纯文本发票 (含所有必要字段),
    满足财务审计要求。生产环境可替换为 reportlab 实现 / wechart-weasyprint。

    Returns:
        写入的文件路径。
    """
    now = datetime.utcnow().isoformat()
    extra = bill.extra_metadata or {}

    content_lines = [
        "═══════════════════════════════════════════════",
        "           HSCredit 衡枢真信 — 发票",
        "═══════════════════════════════════════════════",
        "",
        f"发票号: {invoice_number}",
        f"开票日期: {now}",
        f"付款方: {tenant_name}",
        f"账期: {bill.billing_period}",
        f"计划: {bill.plan}",
        "",
        "───────────────────────────────────────────────",
        "项目明细:",
        "───────────────────────────────────────────────",
        f"  基础订阅费                        ¥ {bill.base_fee:>10.2f}",
        f"  超量 Run 费                       ¥ {bill.overage_runs_fee:>10.2f}",
        f"  超量 Sandbox 时长费                ¥ {bill.overage_duration_fee:>10.2f}",
        f"  超量存储费                       ¥ {bill.overage_storage_fee:>10.2f}",
        "",
        f"  小计 (税前)                       ¥ {extra.get('subtotal', bill.total_amount - extra.get('tax_amount', 0)):>10.2f}",
        f"  增值税 ({extra.get('tax_rate', 0.13)*100:.0f}%)              ¥ {extra.get('tax_amount', 0):>10.2f}",
        "",
        f"  应付总额                           ¥ {bill.total_amount:>10.2f}",
        "",
        "───────────────────────────────────────────────",
        "支付条款:",
        f"  货币: {bill.currency}",
        f"  到期日: {bill.due_date}",
        "  支付通道: 微信 / 支付宝 / 银行转账",
        "",
        "备注: HSCredit 衡枢真信 信用风险建模云平台",
        "      本发票为电子发票, 与纸质发票具有同等法律效力。",
        "",
        "═══════════════════════════════════════════════",
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(content_lines))

    _log.info("invoice_pdf_generated", path=output_path, invoice_number=invoice_number)
    return output_path


async def issue_invoice_for_bill(
    bill: Bill,
    tenant_name: str,
    *,
    pdf_dir: str = "/tmp/invoices",
) -> Invoice:
    """为账单开发票 (Phase 4 B20 验收).

    1. 生成 invoice_number (业务唯一): INV-{period}-{seq}
    2. 生成 PDF
    3. 写 Invoice 表 (status=issued)
    """
    import os

    os.makedirs(pdf_dir, exist_ok=True)

    async with session_scope() as session:
        # seq 计数 (当月已开 + 1)
        # bill.billing_period 格式 YYYY-MM
        year, month = map(int, bill.billing_period.split("-"))
        count = await session.scalar(
            select(func.count(Invoice.invoice_id)).where(
                Invoice.tenant_id == bill.tenant_id,
                Invoice.created_at >= datetime(year, month, 1),
            )
        ) or 0
        seq = int(count) + 1
        invoice_number = f"INV-{bill.billing_period}-{seq:03d}"

        pdf_filename = f"{invoice_number}.txt"  # 简化: 文本发票
        pdf_path = os.path.join(pdf_dir, pdf_filename)

        # PDF 生成 (含租户名称, 来自参数)
        generate_invoice_pdf(
            tenant_name=tenant_name,
            bill=bill,
            output_path=pdf_path,
            invoice_number=invoice_number,
        )

        invoice = Invoice(
            tenant_id=bill.tenant_id,
            bill_id=bill.bill_id,
            invoice_number=invoice_number,
            status="issued",
            amount=bill.total_amount,
            tax_amount=(bill.extra_metadata or {}).get("tax_amount", 0.0),
            pdf_path=pdf_path,
            issued_at=datetime.utcnow(),
        )
        session.add(invoice)
        await session.commit()
        await session.refresh(invoice)
        _log.info("invoice_issued", invoice_number=invoice_number, pdf_path=pdf_path)
        return invoice


# ===== 财务对账导出 =====


async def export_reconciliation_csv(
    *,
    from_period: str | None = None,
    to_period: str | None = None,
) -> str:
    """导出财务对账 CSV (Phase 4 B20 验收).

    Returns:
        CSV 字符串 (含 BOM, Excel 直接打开).
    """
    output = io.StringIO()
    # UTF-8 BOM 让 Excel 正确识别中文
    output.write("﻿")
    writer = csv.writer(output)

    writer.writerow([
        "bill_id", "tenant_id", "billing_period", "plan", "status",
        "base_fee", "overage_runs_fee", "overage_duration_fee", "overage_storage_fee",
        "total_amount", "currency", "due_date", "paid_at", "payment_channel",
    ])

    async with session_scope() as session:
        stmt = select(Bill)
        if from_period:
            stmt = stmt.where(Bill.billing_period >= from_period)
        if to_period:
            stmt = stmt.where(Bill.billing_period <= to_period)
        stmt = stmt.order_by(Bill.billing_period, Bill.tenant_id)

        rows = (await session.execute(stmt)).scalars().all()
        for b in rows:
            writer.writerow([
                str(b.bill_id),
                str(b.tenant_id),
                b.billing_period,
                b.plan,
                b.status,
                b.base_fee,
                b.overage_runs_fee,
                b.overage_duration_fee,
                b.overage_storage_fee,
                b.total_amount,
                b.currency,
                b.due_date.isoformat() if b.due_date else "",
                b.paid_at.isoformat() if b.paid_at else "",
                b.payment_channel or "",
            ])

    return output.getvalue()


# ===== 支付集成 mock (Phase 4 B20 占位) =====


async def create_payment_link(bill: Bill, channel: str = "wechat") -> dict[str, Any]:
    """创建支付链接 (Phase 4 B20 验收).

    真实集成需对接:
    - Stripe: stripe.PaymentLink.create()
    - 微信支付: 统一下单 API
    - 支付宝: 当面付 / 网页支付

    本迭代返回 mock 响应, 用于前端联调与单元测试。
    """
    if channel not in ("stripe", "wechat", "alipay", "manual"):
        raise ValueError(f"不支持的支付通道: {channel}")

    # mock: 返回伪链接
    return {
        "bill_id": str(bill.bill_id),
        "amount": bill.total_amount,
        "currency": bill.currency,
        "channel": channel,
        "payment_url": f"https://pay.example.com/{channel}/{bill.bill_id}",
        "expires_at": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
        "mock": True,
    }


__all__ = [
    "BillComputation",
    "compute_bill",
    "create_payment_link",
    "export_reconciliation_csv",
    "generate_bill_for_tenant",
    "generate_invoice_pdf",
    "issue_invoice_for_bill",
]
