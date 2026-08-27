"""Phase 3 B17 — 节点沙箱资源用量表.

依据 docs/ROADMAP.md Phase 3 B17:

> 每个沙箱 Job 记录 cpu_seconds / mem_peak_mb / duration_ms, 写入 NodeResourceUsage 表,
> 为 Phase 4 计费做数据准备。

新增表:
- node_resource_usage (1:1 关联 node_executions)

不启用 RLS: 这是聚合数据, 按 tenant_id 索引即可, RLS 增加读路径开销。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_node_resource_usage"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "node_resource_usage",
        sa.Column("usage_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("node_exec_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_type", sa.String(length=64), nullable=False),
        sa.Column("cpu_seconds", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("mem_peak_mb", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sandbox_backend", sa.String(length=32), nullable=False, server_default=sa.text("'subprocess'")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'success'")),
        sa.Column("captured_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["node_exec_id"],
            ["node_executions.node_exec_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("node_exec_id", name="uq_node_resource_usage_node_exec"),
        comment="节点沙箱资源用量 (Phase 3 B17)",
    )
    op.create_index("ix_node_resource_usage_tenant", "node_resource_usage", ["tenant_id"])
    op.create_index("ix_node_resource_usage_node_type", "node_resource_usage", ["node_type"])
    op.create_index("ix_node_resource_usage_captured_at", "node_resource_usage", ["captured_at"])


def downgrade() -> None:
    op.drop_index("ix_node_resource_usage_captured_at", table_name="node_resource_usage")
    op.drop_index("ix_node_resource_usage_node_type", table_name="node_resource_usage")
    op.drop_index("ix_node_resource_usage_tenant", table_name="node_resource_usage")
    op.drop_table("node_resource_usage")
