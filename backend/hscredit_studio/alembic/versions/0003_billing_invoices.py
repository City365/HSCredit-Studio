"""Phase 4 B20 — 账单与发票表.

依据 docs/ROADMAP.md Phase 4 B20:

> 月度账单生成 (cron + 异步任务)
> 集成 Stripe / 微信支付 / 支付宝
> PDF 发票生成 (中文模板)
> 财务对账导出

新增表:
- bills (月度账单, 含基础订阅费 + 三维度超量费)
- invoices (发票, 1:N 关联 bills)

不启用 RLS: 财务数据敏感, Phase 5 合规阶段加入细粒度访问控制。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_billing_invoices"
down_revision: str | None = "0002_node_resource_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ===== bills =====
    op.create_table(
        "bills",
        sa.Column("bill_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("billing_period", sa.String(length=16), nullable=False, comment="账期 YYYY-MM"),
        sa.Column("plan", sa.String(length=32), nullable=False, comment="账期对应的 plan"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'draft'"), comment="draft/pending/paid/overdue/voided"),
        sa.Column("base_fee", sa.Float(), nullable=False, server_default=sa.text("0"), comment="基础订阅费 (元)"),
        sa.Column("overage_runs_fee", sa.Float(), nullable=False, server_default=sa.text("0"), comment="超量 Run 费"),
        sa.Column("overage_duration_fee", sa.Float(), nullable=False, server_default=sa.text("0"), comment="超量 Sandbox 时长费"),
        sa.Column("overage_storage_fee", sa.Float(), nullable=False, server_default=sa.text("0"), comment="超量存储费"),
        sa.Column("total_amount", sa.Float(), nullable=False, server_default=sa.text("0"), comment="账单总额"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default=sa.text("'CNY'"), comment="CNY/USD/EUR"),
        sa.Column("due_date", sa.DateTime(timezone=False), nullable=True, comment="到期日"),
        sa.Column("paid_at", sa.DateTime(timezone=False), nullable=True, comment="支付完成时间"),
        sa.Column("payment_channel", sa.String(length=32), nullable=True, comment="stripe/wechat/alipay/manual"),
        sa.Column("extra_metadata", sa.dialects.postgresql.JSONB, nullable=True, comment="扩展元数据 (税率/折扣等)"),
        sa.UniqueConstraint("tenant_id", "billing_period", name="uq_bills_tenant_period"),
        comment="月度账单 (Phase 4 B20)",
    )
    op.create_index("ix_bills_tenant_period", "bills", ["tenant_id", "billing_period"])
    op.create_index("ix_bills_status", "bills", ["status"])

    # ===== invoices =====
    op.create_table(
        "invoices",
        sa.Column("invoice_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("bill_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_number", sa.String(length=64), nullable=False, unique=True, comment="业务唯一发票号"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'draft'"), comment="draft/issued/paid/voided/refunded"),
        sa.Column("amount", sa.Float(), nullable=False, server_default=sa.text("0"), comment="发票金额"),
        sa.Column("tax_amount", sa.Float(), nullable=False, server_default=sa.text("0"), comment="税额"),
        sa.Column("pdf_path", sa.String(length=512), nullable=True, comment="PDF 路径"),
        sa.Column("issued_at", sa.DateTime(timezone=False), nullable=True, comment="开票时间"),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.bill_id"], ondelete="CASCADE"),
        comment="发票 (Phase 4 B20)",
    )
    op.create_index("ix_invoices_bill", "invoices", ["bill_id"])
    op.create_index("ix_invoices_status", "invoices", ["status"])


def downgrade() -> None:
    op.drop_index("ix_invoices_status", table_name="invoices")
    op.drop_index("ix_invoices_bill", table_name="invoices")
    op.drop_table("invoices")

    op.drop_index("ix_bills_status", table_name="bills")
    op.drop_index("ix_bills_tenant_period", table_name="bills")
    op.drop_table("bills")
