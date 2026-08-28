"""Phase 8 B35 — Webhook 投递系统迁移.

依据 docs/ROADMAP.md Phase 8 B35:

> 通用 Webhook 投递系统: 租户订阅平台事件
> HMAC 签名 + 指数退避重试 + 投递日志

本迁移:

- 新增 ``webhook_subscriptions`` 表 — 订阅 (url + secret + events)
- 新增 ``webhook_deliveries`` 表 — 投递记录 (status + 响应 + 重试)
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0013_webhook_subscriptions"
down_revision: str | None = "0012_bi_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ===== 1. webhook_subscriptions =====
    op.create_table(
        "webhook_subscriptions",
        sa.Column(
            "subscription_id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret", sa.String(128), nullable=False),
        sa.Column(
            "events",
            ARRAY(sa.String(64)),
            nullable=True,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "description",
            sa.Text,
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_webhook_subscriptions_tenant_id",
        "webhook_subscriptions",
        ["tenant_id"],
    )

    # ===== 2. webhook_deliveries =====
    op.create_table(
        "webhook_deliveries",
        sa.Column(
            "delivery_id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "subscription_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("webhook_subscriptions.subscription_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("body", sa.LargeBinary, nullable=True),
        sa.Column(
            "attempt",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("response_status", sa.Integer, nullable=True),
        sa.Column("response_body", sa.Text, nullable=True),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_webhook_deliveries_subscription_id",
        "webhook_deliveries",
        ["subscription_id"],
    )
    op.create_index(
        "ix_webhook_deliveries_tenant_id",
        "webhook_deliveries",
        ["tenant_id"],
    )
    op.create_index(
        "ix_webhook_deliveries_event",
        "webhook_deliveries",
        ["event"],
    )
    op.create_index(
        "ix_webhook_deliveries_status",
        "webhook_deliveries",
        ["status"],
    )
    # 复合索引: 后台重试扫描
    op.create_index(
        "ix_webhook_deliveries_status_scheduled",
        "webhook_deliveries",
        ["status", "scheduled_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_deliveries_status_scheduled", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_status", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_event", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_tenant_id", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_subscription_id", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_webhook_subscriptions_tenant_id", table_name="webhook_subscriptions")
    op.drop_table("webhook_subscriptions")


__all__ = ["downgrade", "upgrade"]
