"""节点可插拔 — DB schema 扩展 (Phase 6 B36 节点补齐).

依据 docs/node-plugin/01_DESIGN.md:

扩展现有表 + 新增 2 张表:

- node_definitions: 加 is_custom / owner_tenant_id / source / meta_editable
- custom_nodes: 加 enabled / icon / description / category / current_version_number /
               last_test_run_at / test_run_count / locked_by / locked_at
- node_definition_drafts (新表): 草稿存储, 避免版本历史膨胀
- node_definition_locks (新表): 编辑锁, 防止多人同时编辑

Revision ID: 0015_node_plugin
Revises: 0014_templates_tenant_nullable
Create Date: 2026-09-11 16:35:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "0015_node_plugin"
down_revision = "0014_templates_tenant_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """扩展节点表 + 新增草稿/锁表."""

    # ========== node_definitions 扩展 ==========
    op.add_column(
        "node_definitions",
        sa.Column(
            "is_custom",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="区分系统节点 (false) vs 自定义节点 (true)",
        ),
    )
    op.add_column(
        "node_definitions",
        sa.Column(
            "owner_tenant_id",
            UUID(as_uuid=True),
            nullable=True,
            comment="自定义节点所属租户 (NULL = 系统节点)",
        ),
    )
    op.add_column(
        "node_definitions",
        sa.Column(
            "source",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'system'"),
            comment="节点来源: 'system' / 'custom'",
        ),
    )
    op.add_column(
        "node_definitions",
        sa.Column(
            "meta_editable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="元数据 (name/desc/icon) 是否可被管理员编辑",
        ),
    )
    # 外键: owner_tenant_id -> tenants(tenant_id)
    op.create_foreign_key(
        "fk_node_definitions_owner_tenant",
        "node_definitions",
        "tenants",
        ["owner_tenant_id"],
        ["tenant_id"],
        ondelete="CASCADE",
    )
    # 索引
    op.create_index(
        "ix_node_definitions_tenant",
        "node_definitions",
        ["owner_tenant_id"],
    )
    op.create_index(
        "ix_node_definitions_custom_enabled",
        "node_definitions",
        ["is_custom", "enabled"],
    )
    op.create_index(
        "ix_node_definitions_source",
        "node_definitions",
        ["source"],
    )

    # ========== custom_nodes 扩展 ==========
    op.add_column(
        "custom_nodes",
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="启停控制 (供管理页面开关)",
        ),
    )
    op.add_column(
        "custom_nodes",
        sa.Column(
            "icon",
            sa.String(128),
            nullable=True,
            comment="图标 (emoji)",
        ),
    )
    op.add_column(
        "custom_nodes",
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="节点描述",
        ),
    )
    op.add_column(
        "custom_nodes",
        sa.Column(
            "category",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'特征工程'"),
            comment="节点分类 (前端按 category 分组显示)",
        ),
    )
    op.add_column(
        "custom_nodes",
        sa.Column(
            "current_version_number",
            sa.Integer(),
            nullable=True,
            comment="当前激活版本号 (冗余, 便于直接定位)",
        ),
    )
    op.add_column(
        "custom_nodes",
        sa.Column(
            "last_test_run_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最后一次试运行时间",
        ),
    )
    op.add_column(
        "custom_nodes",
        sa.Column(
            "test_run_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="试运行总次数",
        ),
    )
    op.add_column(
        "custom_nodes",
        sa.Column(
            "locked_by",
            UUID(as_uuid=True),
            nullable=True,
            comment="当前编辑锁持有者 (NULL = 未锁定)",
        ),
    )
    op.add_column(
        "custom_nodes",
        sa.Column(
            "locked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="编辑锁获取时间",
        ),
    )
    # 外键: locked_by -> users(user_id)
    op.create_foreign_key(
        "fk_custom_nodes_locked_by",
        "custom_nodes",
        "users",
        ["locked_by"],
        ["user_id"],
        ondelete="SET NULL",
    )
    # 索引
    op.create_index(
        "ix_custom_nodes_enabled",
        "custom_nodes",
        ["enabled"],
    )
    op.create_index(
        "ix_custom_nodes_tenant_enabled",
        "custom_nodes",
        ["tenant_id", "enabled"],
    )
    op.create_index(
        "ix_custom_nodes_category",
        "custom_nodes",
        ["tenant_id", "category"],
    )

    # ========== 新表: node_definition_drafts (草稿) ==========
    op.create_table(
        "node_definition_drafts",
        sa.Column(
            "draft_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "custom_node_id",
            UUID(as_uuid=True),
            sa.ForeignKey("custom_nodes.custom_node_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("draft_code", sa.Text(), nullable=False, comment="草稿 Python 源码"),
        sa.Column(
            "draft_contract",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="草稿 contract (用户编辑中)",
        ),
        sa.Column(
            "contract_preview",
            JSONB,
            nullable=True,
            comment="AST 反推的 contract 预览 (缓存)",
        ),
        sa.Column(
            "validation_status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'draft'"),
            comment="校验状态: 'draft' / 'validating' / 'valid' / 'invalid'",
        ),
        sa.Column(
            "validation_issues",
            JSONB,
            nullable=True,
            comment="校验 issues 列表 (含行号/规则/消息)",
        ),
        sa.Column(
            "last_validation_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最后一次校验时间",
        ),
        sa.Column(
            "locked_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
            comment="草稿锁定人 (与编辑锁同步)",
        ),
        sa.Column(
            "locked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="草稿锁定时间",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("custom_node_id", name="uq_drafts_custom_node"),
        sa.Index("ix_drafts_validation_status", "validation_status"),
    )

    # ========== 新表: node_definition_locks (编辑锁) ==========
    op.create_table(
        "node_definition_locks",
        sa.Column(
            "lock_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("node_type", sa.String(128), nullable=False, comment="节点类型"),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "locked_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
            comment="锁持有者",
        ),
        sa.Column(
            "locked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="过期时间 (默认 5 分钟后)",
        ),
        sa.UniqueConstraint("node_type", "tenant_id", name="uq_node_locks_type_tenant"),
        sa.Index("ix_node_locks_expires", "expires_at"),
    )


def downgrade() -> None:
    """回滚 — 删除新表, 撤销字段扩展."""

    # ========== 删除新表 ==========
    op.drop_table("node_definition_locks")
    op.drop_table("node_definition_drafts")

    # ========== custom_nodes 字段回滚 ==========
    op.drop_index("ix_custom_nodes_category", table_name="custom_nodes")
    op.drop_index("ix_custom_nodes_tenant_enabled", table_name="custom_nodes")
    op.drop_index("ix_custom_nodes_enabled", table_name="custom_nodes")
    op.drop_constraint("fk_custom_nodes_locked_by", "custom_nodes", type_="foreignkey")
    op.drop_column("custom_nodes", "locked_at")
    op.drop_column("custom_nodes", "locked_by")
    op.drop_column("custom_nodes", "test_run_count")
    op.drop_column("custom_nodes", "last_test_run_at")
    op.drop_column("custom_nodes", "current_version_number")
    op.drop_column("custom_nodes", "category")
    op.drop_column("custom_nodes", "description")
    op.drop_column("custom_nodes", "icon")
    op.drop_column("custom_nodes", "enabled")

    # ========== node_definitions 字段回滚 ==========
    op.drop_index("ix_node_definitions_source", table_name="node_definitions")
    op.drop_index("ix_node_definitions_custom_enabled", table_name="node_definitions")
    op.drop_index("ix_node_definitions_tenant", table_name="node_definitions")
    op.drop_constraint(
        "fk_node_definitions_owner_tenant", "node_definitions", type_="foreignkey"
    )
    op.drop_column("node_definitions", "meta_editable")
    op.drop_column("node_definitions", "source")
    op.drop_column("node_definitions", "owner_tenant_id")
    op.drop_column("node_definitions", "is_custom")
