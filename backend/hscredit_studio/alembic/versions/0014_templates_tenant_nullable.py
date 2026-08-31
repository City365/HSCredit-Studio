"""templates.tenant_id 可空化 — 支持系统模板 (Phase 6 B30).

依据 docs/ROADMAP.md Phase 6 B30:
- 系统模板 (官方模板) ``tenant_id IS NULL`` + ``visibility='public'``, 跨租户可见
- 当前 migration 0001 把 tenant_id 设为 NOT NULL, 导致 ensure_system_templates 启动植入失败
- 修复: ALTER COLUMN DROP NOT NULL
- 影响: 9 个系统模板 (评分卡/规则/监控 + 6 个行业模板) 才能正常植入

Revision ID: 0014_templates_tenant_nullable
Revises: 0013_webhook_subscriptions
Create Date: 2026-08-31 10:32:00.000000

"""
from __future__ import annotations

from alembic import op


revision = "0014_templates_tenant_nullable"
down_revision = "0013_webhook_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """允许 templates.tenant_id 为 NULL — 用于系统模板."""
    op.alter_column("templates", "tenant_id", nullable=True)


def downgrade() -> None:
    """恢复 NOT NULL — 会删除所有 tenant_id IS NULL 的行 (回滚时确认无系统模板)."""
    # 先清理 NULL 行 (系统模板), 否则 NOT NULL 会失败
    op.execute("DELETE FROM templates WHERE tenant_id IS NULL")
    op.alter_column("templates", "tenant_id", nullable=False)
