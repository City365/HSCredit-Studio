"""增值税专票申请 — Phase 4 B21.

依据 docs/ROADMAP.md Phase 4 B21:

> 增值税专票 / 普票申请流程
> 申请 → 审核 → 寄送 (电子发票即时下载 / 纸质发票邮寄)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from hscredit_studio.core.database import session_scope
from hscredit_studio.core.logging import get_logger
from hscredit_studio.models import Bill, Invoice

_log = get_logger(__name__)


@dataclass
class VatInvoiceApplication:
    """增值税专票申请 (Phase 4 B21)."""

    bill_id: UUID
    invoice_type: str  # vat_special / vat_general / receipt
    buyer_tax_id: str  # 购买方税号 (专票必填)
    buyer_name: str
    buyer_address_phone: str
    buyer_bank_account: str
    application_note: str | None = None


def validate_application(app: VatInvoiceApplication) -> list[str]:
    """校验专票申请字段 (Phase 4 B21 验收)."""
    errors: list[str] = []

    if app.invoice_type not in ("vat_special", "vat_general", "receipt"):
        errors.append(f"不支持的发票类型: {app.invoice_type}")

    if not app.buyer_tax_id:
        errors.append("购买方税号必填")

    # 中国税号校验: 15位 / 18位 / 20 位 (含数字与大写字母)
    if app.buyer_tax_id and not (
        15 <= len(app.buyer_tax_id) <= 20
        and all(c.isalnum() and (c.isdigit() or c.isupper()) for c in app.buyer_tax_id)
    ):
        errors.append("税号格式错误 (应为 15-20 位数字或大写字母)")

    if not app.buyer_name:
        errors.append("购买方名称必填")

    if app.invoice_type == "vat_special":
        # 专票额外要求: 地址电话 + 开户行账号
        if not app.buyer_address_phone:
            errors.append("增值税专票需提供地址电话")
        if not app.buyer_bank_account:
            errors.append("增值税专票需提供开户行 + 账号")

    return errors


async def submit_vat_invoice_application(
    tenant_id: UUID,
    application: VatInvoiceApplication,
) -> Invoice:
    """提交专票申请, 创建 Invoice 记录 (status=pending_audit, 待财务审核).

    后续流程 (Phase 5 合规闭环):
    1. 财务审核 buyer_tax_id / buyer_name 真实性
    2. 审核通过 → 状态改 pending_print
    3. 纸质专票 → 邮寄 (更新 status=issued + 写物流单号)
       电子专票 → 即时生成 PDF, status=issued

    当前迭代: 接收申请 + 落库, 不做审核流 (流程依赖 Phase 5 合规角色).
    """
    errors = validate_application(application)
    if errors:
        raise ValueError(f"申请校验失败: {'; '.join(errors)}")

    async with session_scope() as session:
        bill = await session.scalar(
            select(Bill).where(Bill.bill_id == application.bill_id, Bill.tenant_id == tenant_id)
        )
        if bill is None:
            raise ValueError(f"账单不存在: {application.bill_id}")

        # 异步等待财务审核: 这里先创建 draft 状态的 Invoice, 写 buyer 信息
        invoice = Invoice(
            tenant_id=tenant_id,
            bill_id=application.bill_id,
            invoice_number=f"INV-VAT-{application.bill_id.hex[:8]}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            status="draft",
            invoice_type=application.invoice_type,
            amount=bill.total_amount,
            tax_amount=(bill.extra_metadata or {}).get("tax_amount", 0.0),
            buyer_tax_id=application.buyer_tax_id,
            buyer_name=application.buyer_name,
            buyer_address_phone=application.buyer_address_phone,
            buyer_bank_account=application.buyer_bank_account,
            application_note=application.application_note,
        )
        session.add(invoice)
        await session.commit()
        await session.refresh(invoice)
        _log.info(
            "vat_invoice_application_submitted",
            invoice_id=str(invoice.invoice_id),
            invoice_type=application.invoice_type,
            buyer_tax_id_prefix=application.buyer_tax_id[:6] + "***",
        )
        return invoice


__all__ = [
    "VatInvoiceApplication",
    "submit_vat_invoice_application",
    "validate_application",
]
