"""Phase 5 B23 — 通知配置与发送记录表.

依据 docs/ROADMAP.md Phase 5 B23:

> 通知发送记录 (Slack / 企微 / SMTP)
> 通知模板: 账单 / 额度预警 / 告警

新增表:
- notification_configs (租户级通知配置)
- notification_logs (发送历史)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_notifications"
down_revision: str | None = "0004_contracts_vat_invoice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_configs",
        sa.Column("config_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("channel", sa.String(length=32), nullable=False, comment="slack/wecom/email"),
        sa.Column("template_key", sa.String(length=64), nullable=True, comment="None=全模板"),
        sa.Column("recipient", sa.String(length=512), nullable=True, comment="收件人"),
        sa.Column("config", sa.dialects.postgresql.JSONB, nullable=True, comment="扩展配置"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        comment="通知配置 (Phase 5 B23)",
    )
    op.create_index("ix_notification_configs_tenant", "notification_configs", ["tenant_id"])
    op.create_index("ix_notification_configs_channel", "notification_configs", ["channel"])

    op.create_table(
        "notification_logs",
        sa.Column("log_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("template_key", sa.String(length=64), nullable=False, comment="模板键"),
        sa.Column("channel", sa.String(length=32), nullable=False, comment="slack/wecom/email"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'pending'"), comment="pending/sent/failed/dry_run"),
        sa.Column("title", sa.String(length=256), nullable=False, comment="通知标题"),
        sa.Column("body", sa.Text(), nullable=False, comment="通知正文"),
        sa.Column("recipient", sa.String(length=512), nullable=True, comment="收件人"),
        sa.Column("error", sa.Text(), nullable=True, comment="失败错误"),
        comment="通知发送历史 (Phase 5 B23)",
    )
    op.create_index("ix_notification_logs_tenant_created", "notification_logs", ["tenant_id", "created_at"])
    op.create_index("ix_notification_logs_status", "notification_logs", ["status"])
    op.create_index("ix_notification_logs_template", "notification_logs", ["template_key"])


def downgrade() -> None:
    op.drop_index("ix_notification_logs_template", table_name="notification_logs")
    op.drop_index("ix_notification_logs_status", table_name="notification_logs")
    op.drop_index("ix_notification_logs_tenant_created", table_name="notification_logs")
    op.drop_table("notification_logs")

    op.drop_index("ix_notification_configs_channel", table_name="notification_configs")
    op.drop_index("ix_notification_configs_tenant", table_name="notification_configs")
    op.drop_table("notification_configs")
