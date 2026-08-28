"""Phase 7 B33 — BI 数据库视图迁移.

依据 docs/ROADMAP.md Phase 7 B33:

> 数据库视图 (用于 PowerBI / Tableau / FineBI 直接连接)

本迁移:

- 创建 4 个 BI 专用视图:
  - ``v_bi_audit_recent``  — 近 90 天审计事件 (扁平化)
  - ``v_bi_run_summary``   — Run 汇总 (按 workflow 聚合)
  - ``v_bi_usage_daily``   — 用量按日聚合
  - ``v_bi_billing_summary`` — 账单汇总
- 提供 GRANT SELECT 给 bi_reader 角色 (生产环境)
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012_bi_views"
down_revision: str | None = "0011_template_sharing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ===== 1. v_bi_audit_recent — 近 90 天审计事件 =====
    op.execute(
        """
        CREATE OR REPLACE VIEW v_bi_audit_recent AS
        SELECT
            event_id,
            tenant_id,
            user_id,
            action,
            resource_type,
            resource_id,
            ip_address,
            occurred_at,
            details
        FROM audit_events
        WHERE occurred_at >= (NOW() - INTERVAL '90 days')
        """
    )

    # ===== 2. v_bi_run_summary — Run 汇总 =====
    op.execute(
        """
        CREATE OR REPLACE VIEW v_bi_run_summary AS
        SELECT
            r.run_id,
            r.tenant_id,
            r.workflow_id,
            r.run_number,
            r.status,
            r.started_at,
            r.finished_at,
            CASE
                WHEN r.started_at IS NOT NULL AND r.finished_at IS NOT NULL
                THEN EXTRACT(EPOCH FROM (r.finished_at - r.started_at)) * 1000
                ELSE 0
            END AS duration_ms,
            (SELECT COUNT(*) FROM node_executions ne WHERE ne.run_id = r.run_id) AS node_count,
            r.created_at,
            r.updated_at
        FROM runs r
        """
    )

    # ===== 3. v_bi_usage_daily — 用量按日聚合 =====
    op.execute(
        """
        CREATE OR REPLACE VIEW v_bi_usage_daily AS
        SELECT
            DATE_TRUNC('day', r.created_at)::date AS usage_date,
            r.tenant_id,
            COUNT(r.run_id) AS runs_count,
            COALESCE(
                SUM(
                    CASE
                        WHEN r.started_at IS NOT NULL AND r.finished_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (r.finished_at - r.started_at)) * 1000
                        ELSE 0
                    END
                ),
                0
            ) AS duration_ms,
            COUNT(*) FILTER (WHERE r.status = 'failed') AS failed_count,
            COUNT(*) FILTER (WHERE r.status = 'success') AS success_count
        FROM runs r
        GROUP BY DATE_TRUNC('day', r.created_at), r.tenant_id
        """
    )

    # ===== 4. v_bi_billing_summary — 账单汇总 =====
    op.execute(
        """
        CREATE OR REPLACE VIEW v_bi_billing_summary AS
        SELECT
            b.bill_id,
            b.tenant_id,
            b.billing_period,
            b.plan,
            b.status,
            b.base_fee,
            b.overage_runs_fee,
            b.overage_duration_fee,
            b.overage_storage_fee,
            b.total_amount,
            b.currency,
            b.due_date,
            b.paid_at,
            b.payment_channel,
            b.created_at
        FROM bills b
        """
    )

    # ===== 5. 给 bi_reader 角色授予 SELECT (生产环境建议) =====
    # 开发环境可能无 bi_reader 角色, 用 IF EXISTS 保护
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bi_reader') THEN
                GRANT SELECT ON v_bi_audit_recent TO bi_reader;
                GRANT SELECT ON v_bi_run_summary TO bi_reader;
                GRANT SELECT ON v_bi_usage_daily TO bi_reader;
                GRANT SELECT ON v_bi_billing_summary TO bi_reader;
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_bi_billing_summary")
    op.execute("DROP VIEW IF EXISTS v_bi_usage_daily")
    op.execute("DROP VIEW IF EXISTS v_bi_run_summary")
    op.execute("DROP VIEW IF EXISTS v_bi_audit_recent")


__all__ = ["downgrade", "upgrade"]
