"""Phase 5 B27 — 告警相关表迁移.

依据 docs/ROADMAP.md Phase 5 B27:

> Alertmanager 集成 + 分级路由 (warning → 邮件, critical → 企微+电话)
> 告警抑制与静默规则

新增表:
- alert_rules (告警规则)
- alert_instances (活跃告警实例)
- alert_silences (静默规则)
- alert_history (发送历史)
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_alert"
down_revision: str | None = "0007_pipl"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("rule_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("group", sa.String(length=64), nullable=False, server_default=sa.text("'default'")),
        sa.Column("promql", sa.Text(), nullable=False),
        sa.Column("for_duration", sa.String(length=16), nullable=False, server_default=sa.text("'5m'")),
        sa.Column("severity", sa.String(length=16), nullable=False, comment="info/warning/critical/page"),
        sa.Column("summary", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        comment="告警规则 (Phase 5 B27)",
    )
    op.create_index("ix_alert_rules_group", "alert_rules", ["group"])
    op.create_index("ix_alert_rules_severity", "alert_rules", ["severity"])
    op.create_index("ix_alert_rules_enabled", "alert_rules", ["enabled"])

    op.create_table(
        "alert_instances",
        sa.Column("instance_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("fingerprint", sa.String(length=32), nullable=False, unique=True),
        sa.Column("alert_name", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default=sa.text("'firing'")),
        sa.Column("labels", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("annotations", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("value", sa.String(length=64), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        comment="活跃告警实例 (Phase 5 B27)",
    )
    op.create_index("ix_alert_instances_state", "alert_instances", ["state"])
    op.create_index("ix_alert_instances_severity", "alert_instances", ["severity"])
    op.create_index("ix_alert_instances_starts_at", "alert_instances", ["starts_at"])

    op.create_table(
        "alert_silences",
        sa.Column("silence_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("matchers", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False, server_default=sa.text("'system'")),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        comment="告警静默规则 (Phase 5 B27)",
    )
    op.create_index("ix_alert_silences_active", "alert_silences", ["starts_at", "ends_at"])
    op.create_index("ix_alert_silences_active_flag", "alert_silences", ["active"])

    op.create_table(
        "alert_history",
        sa.Column("history_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("alert_name", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("channels", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("receiver", sa.String(length=64), nullable=True),
        sa.Column("labels", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("suppressed_reason", sa.String(length=256), nullable=True),
        comment="告警发送历史 (Phase 5 B27)",
    )
    op.create_index("ix_alert_history_sent_at", "alert_history", ["sent_at"])
    op.create_index("ix_alert_history_severity", "alert_history", ["severity"])


def downgrade() -> None:
    op.drop_index("ix_alert_history_severity", table_name="alert_history")
    op.drop_index("ix_alert_history_sent_at", table_name="alert_history")
    op.drop_table("alert_history")

    op.drop_index("ix_alert_silences_active_flag", table_name="alert_silences")
    op.drop_index("ix_alert_silences_active", table_name="alert_silences")
    op.drop_table("alert_silences")

    op.drop_index("ix_alert_instances_starts_at", table_name="alert_instances")
    op.drop_index("ix_alert_instances_severity", table_name="alert_instances")
    op.drop_index("ix_alert_instances_state", table_name="alert_instances")
    op.drop_table("alert_instances")

    op.drop_index("ix_alert_rules_enabled", table_name="alert_rules")
    op.drop_index("ix_alert_rules_severity", table_name="alert_rules")
    op.drop_index("ix_alert_rules_group", table_name="alert_rules")
    op.drop_table("alert_rules")
