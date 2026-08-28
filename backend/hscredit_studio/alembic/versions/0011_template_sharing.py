"""Phase 6 B31 — 自定义模板共享迁移.

依据 docs/ROADMAP.md Phase 6 B31:

> 租户可将自定义工作流发布为租户内模板
> 跨租户模板市场 (可选, 治理复杂度高)
> 风险: 跨租户模板涉及 IP / 数据安全, 需先有模板审核流程

本迁移:

- 新增 :attr:`Template.review_status` (draft / pending / approved / rejected)
- 新增 :attr:`Template.shared_with_tenants` JSONB 数组 (跨租户白名单)
- 新增 :attr:`Template.rejection_reason` TEXT (审核拒绝原因)
- 新增 :class:`TemplateReviewLog` 审核日志 (谁在何时审核了哪个模板)
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0011_template_sharing"
down_revision: str | None = "0010_rbac_fix_updated_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


REVIEW_STATUS_VALUES = ("draft", "pending", "approved", "rejected")


def upgrade() -> None:
    # ===== 1. templates 表扩展字段 =====
    op.add_column(
        "templates",
        sa.Column(
            "review_status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'draft'"),
            comment=f"审核状态: {REVIEW_STATUS_VALUES}",
        ),
    )
    op.add_column(
        "templates",
        sa.Column(
            "rejection_reason",
            sa.Text(),
            nullable=True,
            comment="审核拒绝原因",
        ),
    )
    op.add_column(
        "templates",
        sa.Column(
            "shared_with_tenants",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="跨租户白名单 (tenant_id 数组)",
        ),
    )
    op.add_column(
        "templates",
        sa.Column(
            "source_workflow_id",
            PGUUID(as_uuid=True),
            nullable=True,
            comment="来源 workflow_id (从工作流发布时填充)",
        ),
    )
    op.create_index(
        "ix_templates_review_status",
        "templates",
        ["review_status"],
    )
    op.create_index(
        "ix_templates_source_workflow",
        "templates",
        ["source_workflow_id"],
        postgresql_where=sa.text("source_workflow_id IS NOT NULL"),
    )

    # ===== 2. template_review_logs 表 =====
    op.create_table(
        "template_review_logs",
        sa.Column("log_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("template_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_id", PGUUID(as_uuid=True), nullable=False, comment="审核人 user_id"),
        sa.Column("old_status", sa.String(length=16), nullable=True, comment="变更前状态"),
        sa.Column("new_status", sa.String(length=16), nullable=False, comment="变更后状态"),
        sa.Column("comment", sa.Text(), nullable=True, comment="审核备注"),
        sa.Column(
            "extra",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_template_review_logs_template",
        "template_review_logs",
        ["template_id"],
    )
    op.create_index(
        "ix_template_review_logs_reviewer",
        "template_review_logs",
        ["reviewer_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_template_review_logs_reviewer", table_name="template_review_logs")
    op.drop_index("ix_template_review_logs_template", table_name="template_review_logs")
    op.drop_table("template_review_logs")

    op.drop_index("ix_templates_source_workflow", table_name="templates")
    op.drop_index("ix_templates_review_status", table_name="templates")
    op.drop_column("templates", "source_workflow_id")
    op.drop_column("templates", "shared_with_tenants")
    op.drop_column("templates", "rejection_reason")
    op.drop_column("templates", "review_status")
