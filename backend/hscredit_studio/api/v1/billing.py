"""账单与发票 API — Phase 4 B20.

依据 docs/ROADMAP.md Phase 4 B20 验收:

- ``GET  /api/v1/{tenant}/bills`` — 列出账单
- ``POST /api/v1/{tenant}/bills`` — 生成当月账单 (admin)
- ``GET  /api/v1/{tenant}/bills/{bill_id}`` — 账单详情 (含发票列表)
- ``POST /api/v1/{tenant}/bills/{bill_id}/invoice`` — 开发票
- ``POST /api/v1/{tenant}/bills/{bill_id}/pay`` — 创建支付链接 (mock)
- ``GET  /api/v1/{tenant}/reconciliation`` — 财务对账 CSV 导出
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep
from hscredit_studio.models import Bill, Invoice, Tenant
from hscredit_studio.services.billing import (
    create_payment_link,
    export_reconciliation_csv,
    generate_bill_for_tenant,
    issue_invoice_for_bill,
)

router = APIRouter(tags=["账单"])


@router.get(
    "",
    summary="租户账单列表",
)
async def list_bills(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """列出租户账单 (按账期降序)."""
    tid = UUID(tenant_id)
    bills = (
        await session.execute(
            select(Bill)
            .where(Bill.tenant_id == tid)
            .order_by(Bill.billing_period.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "bill_id": str(b.bill_id),
                "billing_period": b.billing_period,
                "plan": b.plan,
                "status": b.status,
                "total_amount": b.total_amount,
                "currency": b.currency,
                "due_date": b.due_date.isoformat() if b.due_date else None,
                "paid_at": b.paid_at.isoformat() if b.paid_at else None,
                "payment_channel": b.payment_channel,
            }
            for b in bills
        ],
        "count": len(bills),
    }


@router.post(
    "",
    summary="生成当月账单",
    description="触发账期账单生成 (幂等: 重复账期返回已存在)",
)
async def create_bill(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    billing_period: str = Query(
        default="",
        description="账期 YYYY-MM (默认当前月)",
    ),
) -> dict[str, Any]:
    """Phase 4 B20 — 生成账单."""
    tid = UUID(tenant_id)
    if not billing_period:
        now = datetime.utcnow()
        billing_period = f"{now.year:04d}-{now.month:02d}"

    # 查 plan
    plan = await session.scalar(select(Tenant.plan).where(Tenant.tenant_id == tid)) or "free"

    bill = await generate_bill_for_tenant(tid, plan, billing_period)
    return {
        "bill_id": str(bill.bill_id),
        "billing_period": bill.billing_period,
        "plan": bill.plan,
        "status": bill.status,
        "base_fee": bill.base_fee,
        "overage_runs_fee": bill.overage_runs_fee,
        "overage_duration_fee": bill.overage_duration_fee,
        "overage_storage_fee": bill.overage_storage_fee,
        "total_amount": bill.total_amount,
        "currency": bill.currency,
        "due_date": bill.due_date.isoformat() if bill.due_date else None,
    }


@router.get(
    "/{bill_id}",
    summary="账单详情",
)
async def get_bill(
    bill_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
) -> dict[str, Any]:
    """Phase 4 B20 — 账单详情含发票列表."""
    tid = UUID(tenant_id)
    bill = await session.scalar(
        select(Bill).where(Bill.bill_id == bill_id, Bill.tenant_id == tid)
    )
    if bill is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="账单不存在")
    invoices = (
        await session.execute(
            select(Invoice).where(Invoice.bill_id == bill_id).order_by(Invoice.created_at)
        )
    ).scalars().all()
    return {
        "bill_id": str(bill.bill_id),
        "billing_period": bill.billing_period,
        "plan": bill.plan,
        "status": bill.status,
        "base_fee": bill.base_fee,
        "overage_runs_fee": bill.overage_runs_fee,
        "overage_duration_fee": bill.overage_duration_fee,
        "overage_storage_fee": bill.overage_storage_fee,
        "total_amount": bill.total_amount,
        "currency": bill.currency,
        "due_date": bill.due_date.isoformat() if bill.due_date else None,
        "paid_at": bill.paid_at.isoformat() if bill.paid_at else None,
        "extra_metadata": bill.extra_metadata,
        "invoices": [
            {
                "invoice_id": str(i.invoice_id),
                "invoice_number": i.invoice_number,
                "status": i.status,
                "amount": i.amount,
                "tax_amount": i.tax_amount,
                "pdf_path": i.pdf_path,
                "issued_at": i.issued_at.isoformat() if i.issued_at else None,
            }
            for i in invoices
        ],
    }


@router.post(
    "/{bill_id}/invoice",
    summary="开发票",
)
async def issue_invoice(
    bill_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
) -> dict[str, Any]:
    """Phase 4 B20 — 为账单开发票 (中文 PDF)."""
    tid = UUID(tenant_id)
    bill = await session.scalar(
        select(Bill).where(Bill.bill_id == bill_id, Bill.tenant_id == tid)
    )
    if bill is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="账单不存在")
    tenant = await session.scalar(select(Tenant).where(Tenant.tenant_id == tid))
    tenant_name = tenant.name if tenant else f"租户-{tid.hex[:8]}"
    invoice = await issue_invoice_for_bill(bill, tenant_name)
    return {
        "invoice_id": str(invoice.invoice_id),
        "invoice_number": invoice.invoice_number,
        "status": invoice.status,
        "amount": invoice.amount,
        "pdf_path": invoice.pdf_path,
        "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
    }


@router.post(
    "/{bill_id}/pay",
    summary="创建支付链接",
)
async def create_pay_link(
    bill_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    channel: str = Query(default="wechat", pattern="^(stripe|wechat|alipay|manual)$"),
) -> dict[str, Any]:
    """Phase 4 B20 — 创建支付链接 (mock, 真实集成留 B22 之后)."""
    tid = UUID(tenant_id)
    bill = await session.scalar(
        select(Bill).where(Bill.bill_id == bill_id, Bill.tenant_id == tid)
    )
    if bill is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="账单不存在")
    return await create_payment_link(bill, channel)


@router.get(
    "/reconciliation/csv",
    summary="财务对账 CSV 导出",
    response_class=PlainTextResponse,
)
async def reconciliation_csv(
    tenant_id: TenantDep,
    _: CurrentUserDep,
    from_period: str | None = Query(default=None, description="起始账期 YYYY-MM"),
    to_period: str | None = Query(default=None, description="截止账期 YYYY-MM"),
) -> str:
    """Phase 4 B20 — 财务对账 CSV 导出 (含 BOM, Excel 直接打开)."""
    csv_text = await export_reconciliation_csv(
        from_period=from_period,
        to_period=to_period,
    )
    return csv_text


__all__ = ["router"]
