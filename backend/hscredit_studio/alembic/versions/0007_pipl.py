"""Phase 5 B26 PIPL — 数据库迁移.

依据 docs/ROADMAP.md Phase 5 B26:

> 用户权利实现: 查询、更正、删除、可携
> 数据流图 + 跨境传输审批

新增表:
- consent_records (用户同意记录)
- data_subject_requests (数据主体请求)
- cross_border_transfers (跨境传输审批)
- privacy_policy_versions (隐私政策版本)
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_pipl"
down_revision: str | None = "0006_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consent_records",
        sa.Column("consent_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False, comment="service_provision/billing/marketing/analytics/third_party_sharing"),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("policy_version", sa.String(length=32), nullable=False, server_default=sa.text("'v1.0'")),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True, comment="撤回时间 NULL=仍有效"),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        comment="用户同意记录 (Phase 5 B26)",
    )
    op.create_index("ix_consent_user_purpose", "consent_records", ["user_id", "purpose"])
    op.create_index("ix_consent_tenant_granted", "consent_records", ["tenant_id", "granted"])
    op.create_index("ix_consent_revoked", "consent_records", ["revoked_at"])

    op.create_table(
        "data_subject_requests",
        sa.Column("request_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_type", sa.String(length=32), nullable=False, comment="access/correction/deletion/portability/withdraw_consent"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'submitted'")),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("response", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False, comment="法定 30 天截止"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processor_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        comment="数据主体请求 (Phase 5 B26)",
    )
    op.create_index("ix_dsr_user_type", "data_subject_requests", ["tenant_id", "user_id", "request_type"])
    op.create_index("ix_dsr_status", "data_subject_requests", ["tenant_id", "status"])
    op.create_index("ix_dsr_due_at", "data_subject_requests", ["due_at"])

    op.create_table(
        "cross_border_transfers",
        sa.Column("transfer_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("destination_country", sa.String(length=8), nullable=False, comment="ISO 3166-1 alpha-2"),
        sa.Column("destination_entity", sa.String(length=256), nullable=False),
        sa.Column("data_categories", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("legal_basis", sa.String(length=64), nullable=False, comment="cac_assessment/standard_contract/certification/explicit_consent"),
        sa.Column("legal_basis_ref", sa.String(length=256), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=True, comment="NULL=待审"),
        sa.Column("approver_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        comment="跨境数据传输审批 (Phase 5 B26)",
    )
    op.create_index("ix_cross_border_destination", "cross_border_transfers", ["destination_country"])
    op.create_index("ix_cross_border_status", "cross_border_transfers", ["approved"])
    op.create_index("ix_cross_border_user", "cross_border_transfers", ["user_id"])

    op.create_table(
        "privacy_policy_versions",
        sa.Column("version", sa.String(length=32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        comment="隐私政策版本 (Phase 5 B26)",
    )
    op.create_index("ix_privacy_policy_current", "privacy_policy_versions", ["is_current"])


def downgrade() -> None:
    op.drop_index("ix_privacy_policy_current", table_name="privacy_policy_versions")
    op.drop_table("privacy_policy_versions")

    op.drop_index("ix_cross_border_user", table_name="cross_border_transfers")
    op.drop_index("ix_cross_border_status", table_name="cross_border_transfers")
    op.drop_index("ix_cross_border_destination", table_name="cross_border_transfers")
    op.drop_table("cross_border_transfers")

    op.drop_index("ix_dsr_due_at", table_name="data_subject_requests")
    op.drop_index("ix_dsr_status", table_name="data_subject_requests")
    op.drop_index("ix_dsr_user_type", table_name="data_subject_requests")
    op.drop_table("data_subject_requests")

    op.drop_index("ix_consent_revoked", table_name="consent_records")
    op.drop_index("ix_consent_tenant_granted", table_name="consent_records")
    op.drop_index("ix_consent_user_purpose", table_name="consent_records")
    op.drop_table("consent_records")
