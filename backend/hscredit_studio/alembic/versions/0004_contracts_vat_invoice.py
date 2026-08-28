"""Phase 4 B21 — 合同 + 增值税专票字段.

依据 docs/ROADMAP.md Phase 4 B21:

> 增值税专票 / 普票申请流程
> 合同 PDF 模板 (电子签章占位)
> 与 B20 支付成功自动开收据

新增/修改:

- invoices 表添加 invoice_type + buyer_tax_id / buyer_name / address / bank_account / application_note
- 新增 contracts 表
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_contracts_vat_invoice"
down_revision: str | None = "0003_billing_invoices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ===== invoices: 新增专票字段 =====
    op.add_column("invoices", sa.Column("invoice_type", sa.String(length=16), nullable=False, server_default=sa.text("'normal'"), comment="发票类型"))
    op.add_column("invoices", sa.Column("buyer_tax_id", sa.String(length=64), nullable=True, comment="购买方税号"))
    op.add_column("invoices", sa.Column("buyer_name", sa.String(length=256), nullable=True, comment="购买方名称"))
    op.add_column("invoices", sa.Column("buyer_address_phone", sa.String(length=256), nullable=True, comment="购买方地址电话"))
    op.add_column("invoices", sa.Column("buyer_bank_account", sa.String(length=128), nullable=True, comment="购买方开户行 + 账号"))
    op.add_column("invoices", sa.Column("application_note", sa.Text(), nullable=True, comment="专票申请备注"))
    op.create_index("ix_invoices_type", "invoices", ["invoice_type"])

    # ===== contracts =====
    op.create_table(
        "contracts",
        sa.Column("contract_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("contract_number", sa.String(length=64), nullable=False, unique=True, comment="业务唯一合同号"),
        sa.Column("contract_type", sa.String(length=32), nullable=False, comment="service_agreement/dpa/nda/quote"),
        sa.Column("title", sa.String(length=256), nullable=False, comment="合同标题"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'draft'"), comment="draft/pending_signature/signed/archived/voided"),
        sa.Column("valid_from", sa.DateTime(timezone=False), nullable=True, comment="生效日"),
        sa.Column("valid_until", sa.DateTime(timezone=False), nullable=True, comment="到期日"),
        sa.Column("signed_at", sa.DateTime(timezone=False), nullable=True, comment="签约时间"),
        sa.Column("pdf_path", sa.String(length=512), nullable=True, comment="PDF 路径"),
        sa.Column("extra_metadata", sa.dialects.postgresql.JSONB, nullable=True, comment="扩展元数据"),
        comment="合同 (Phase 4 B21)",
    )
    op.create_index("ix_contracts_tenant_status", "contracts", ["tenant_id", "status"])
    op.create_index("ix_contracts_type", "contracts", ["contract_type"])


def downgrade() -> None:
    op.drop_index("ix_contracts_type", table_name="contracts")
    op.drop_index("ix_contracts_tenant_status", table_name="contracts")
    op.drop_table("contracts")

    op.drop_index("ix_invoices_type", table_name="invoices")
    op.drop_column("invoices", "application_note")
    op.drop_column("invoices", "buyer_bank_account")
    op.drop_column("invoices", "buyer_address_phone")
    op.drop_column("invoices", "buyer_name")
    op.drop_column("invoices", "buyer_tax_id")
    op.drop_column("invoices", "invoice_type")
