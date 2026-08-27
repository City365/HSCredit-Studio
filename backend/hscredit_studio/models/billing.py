"""账单与发票模型 — Phase 4 B20.

依据 docs/ROADMAP.md Phase 4 B20:

> 月度账单生成 (cron + 异步任务)
> 集成 Stripe / 微信支付 / 支付宝
> PDF 发票生成 (中文模板)
> 财务对账导出

表设计:

- ``bills`` — 月度账单 (按 tenant + billing_period), 含基础订阅费 + 超量费
- ``invoices`` — 发票 (账单可拆分为多张发票), 含 PDF 路径 + 状态
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hscredit_studio.core.database import Base
from hscredit_studio.models.base import (
    ModelSerializerMixin,
    TenantMixin,
    TimestampMixin,
)

BILL_STATUS_VALUES = ("draft", "pending", "paid", "overdue", "voided")
INVOICE_STATUS_VALUES = ("draft", "issued", "paid", "voided", "refunded")
PAYMENT_CHANNEL_VALUES = ("stripe", "wechat", "alipay", "manual")


class Bill(Base, TimestampMixin, TenantMixin, ModelSerializerMixin):
    """月度账单 (Phase 4 B20).

    计费维度:
    - ``base_fee``: 基础订阅费 (按 plan)
    - ``overage_runs_fee``: 超量 Run 费
    - ``overage_duration_fee``: 超量 Sandbox 时长费
    - ``overage_storage_fee``: 超量存储费
    - ``total_amount``: 总额
    - ``currency``: 货币 (默认 CNY)
    """

    __tablename__ = "bills"

    bill_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    billing_period: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="账期 YYYY-MM",
    )
    plan: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="账期对应的 plan (free/pro/enterprise)",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'draft'"),
        comment=f"账单状态 {BILL_STATUS_VALUES}",
    )
    base_fee: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0"),
        comment="基础订阅费 (元)",
    )
    overage_runs_fee: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0"),
        comment="超量 Run 费 (元)",
    )
    overage_duration_fee: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0"),
        comment="超量 Sandbox 时长费 (元)",
    )
    overage_storage_fee: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0"),
        comment="超量存储费 (元)",
    )
    total_amount: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0"),
        comment="账单总额 (元)",
    )
    currency: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        server_default=text("'CNY'"),
        comment="货币 (CNY/USD/EUR)",
    )
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        comment="到期日 (UTC)",
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        comment="支付完成时间 (UTC)",
    )
    payment_channel: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment=f"支付通道 {PAYMENT_CHANNEL_VALUES}",
    )
    extra_metadata: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="扩展元数据 (税率/折扣/退款记录等)",
    )

    invoices: Mapped[list[Invoice]] = relationship(
        "Invoice",
        back_populates="bill",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "billing_period", name="uq_bills_tenant_period"),
        Index("ix_bills_tenant_period", "tenant_id", "billing_period"),
        Index("ix_bills_status", "status"),
    )


class Invoice(Base, TimestampMixin, TenantMixin, ModelSerializerMixin):
    """发票 (Phase 4 B20).

    一张账单可拆分为多张发票 (按支付通道或分期), 每张发票含独立 PDF 路径。
    """

    __tablename__ = "invoices"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    bill_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("bills.bill_id", ondelete="CASCADE"),
        nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="发票号 (业务唯一, 例: INV-202608-001)",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'draft'"),
        comment=f"发票状态 {INVOICE_STATUS_VALUES}",
    )
    amount: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0"),
        comment="发票金额 (元)",
    )
    tax_amount: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0"),
        comment="税额 (元)",
    )
    pdf_path: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="PDF 文件路径 (本地或对象存储 key)",
    )
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        comment="开票时间 (UTC)",
    )

    bill: Mapped[Bill] = relationship("Bill", back_populates="invoices")

    __table_args__ = (
        Index("ix_invoices_bill", "bill_id"),
        Index("ix_invoices_status", "status"),
    )


__all__ = [
    "BILL_STATUS_VALUES",
    "INVOICE_STATUS_VALUES",
    "PAYMENT_CHANNEL_VALUES",
    "Bill",
    "Invoice",
]
