"""Phase 5 B25 — 安全加固相关表迁移.

依据 docs/ROADMAP.md Phase 5 B25:

> 等保差距整改（认证 / 访问控制 / 安全审计 / 入侵防范 / 数据保护 / 备份恢复）

新增表:
- ip_access_rules (访问控制 - IP 白/黑名单)
- account_lockouts (认证加固 - 失败锁定)
- vulnerabilities (渗透测试闭环)
- audit_chain_checkpoints (安全审计 - 链检查日志)
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_security"
down_revision: str | None = "0005_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ip_access_rules",
        sa.Column("rule_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("rule_type", sa.String(length=16), nullable=False, comment="whitelist/blacklist"),
        sa.Column("cidr", sa.String(length=64), nullable=False, comment="CIDR 网段或单 IP"),
        sa.Column("description", sa.String(length=256), nullable=True, comment="备注"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        comment="租户 IP 访问规则 (Phase 5 B25)",
    )
    op.create_index("ix_ip_access_rules_tenant_type", "ip_access_rules", ["tenant_id", "rule_type"])
    op.create_index("ix_ip_access_rules_enabled", "ip_access_rules", ["tenant_id", "enabled"])

    op.create_table(
        "account_lockouts",
        sa.Column("lockout_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email_hash", sa.String(length=64), nullable=True, comment="邮箱 hash (避免明文)"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("last_ip", sa.dialects.postgresql.INET(), nullable=True),
        comment="账号登录失败锁定 (Phase 5 B25)",
    )
    op.create_index("ix_account_lockouts_user", "account_lockouts", ["tenant_id", "user_id"])
    op.create_index("ix_account_lockouts_email", "account_lockouts", ["tenant_id", "email_hash"])
    op.create_index("ix_account_lockouts_until", "account_lockouts", ["locked_until"])

    op.create_table(
        "vulnerabilities",
        sa.Column("vuln_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, comment="low/medium/high/critical"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("remediation", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'open'")),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fix_notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=True),
        comment="渗透测试发现项 (Phase 5 B25)",
    )
    op.create_index("ix_vulnerabilities_status", "vulnerabilities", ["status"])
    op.create_index("ix_vulnerabilities_severity", "vulnerabilities", ["severity"])
    op.create_index("ix_vulnerabilities_discovered", "vulnerabilities", ["discovered_at"])

    op.create_table(
        "audit_chain_checkpoints",
        sa.Column("checkpoint_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, comment="ok/broken/missing_secret"),
        sa.Column("checked_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_event_id", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("window_hours", sa.Integer(), nullable=False, server_default=sa.text("24")),
        sa.Column("details", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="审计链完整性检查日志 (Phase 5 B25)",
    )
    op.create_index("ix_audit_chain_checkpoints_status", "audit_chain_checkpoints", ["status"])
    op.create_index("ix_audit_chain_checkpoints_checked_at", "audit_chain_checkpoints", ["checked_at"])
    op.create_index("ix_audit_chain_checkpoints_tenant", "audit_chain_checkpoints", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_chain_checkpoints_tenant", table_name="audit_chain_checkpoints")
    op.drop_index("ix_audit_chain_checkpoints_checked_at", table_name="audit_chain_checkpoints")
    op.drop_index("ix_audit_chain_checkpoints_status", table_name="audit_chain_checkpoints")
    op.drop_table("audit_chain_checkpoints")

    op.drop_index("ix_vulnerabilities_discovered", table_name="vulnerabilities")
    op.drop_index("ix_vulnerabilities_severity", table_name="vulnerabilities")
    op.drop_index("ix_vulnerabilities_status", table_name="vulnerabilities")
    op.drop_table("vulnerabilities")

    op.drop_index("ix_account_lockouts_until", table_name="account_lockouts")
    op.drop_index("ix_account_lockouts_email", table_name="account_lockouts")
    op.drop_index("ix_account_lockouts_user", table_name="account_lockouts")
    op.drop_table("account_lockouts")

    op.drop_index("ix_ip_access_rules_enabled", table_name="ip_access_rules")
    op.drop_index("ix_ip_access_rules_tenant_type", table_name="ip_access_rules")
    op.drop_table("ip_access_rules")
