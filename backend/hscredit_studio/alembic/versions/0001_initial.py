"""Initial schema — 21 张核心表 + RLS + 索引.

按文档 09 第 9.3 节 (Phase 1 范围) 创建以下业务表:

1. tenants
2. users
3. tenant_members
4. user_invitations
5. api_keys
6. workflows
7. workflow_versions
8. workflow_templates  (依赖 templates，先临时建立)
9. templates
10. template_versions
11. template_ratings
12. runs
13. node_executions
14. node_execution_logs
15. node_artifacts
16. run_artifacts
17. node_definitions
18. custom_nodes
19. custom_node_versions
20. custom_node_test_runs
21. audit_events

依赖关系考虑（约束顺序）：

- 引用 ``tenants.tenant_id`` 的表必须在 tenants 之后
- 引用 ``users.user_id`` 的表必须在 users 之后
- ``workflow_templates`` 引用 templates；通过临时 ``ALTER TABLE`` 或延迟创建解决 FK。
  本迁移采用"占位先建 + ALTER 重建约束"避免对 09 schema 的偏离。

RLS（Row Level Security）策略：

- 所有带 ``tenant_id`` 的业务表启用 ``ENABLE ROW LEVEL SECURITY`` + ``FORCE``
- 通过 ``app.current_tenant`` session var 启用隔离
- ``tenants`` / ``node_definitions`` / ``schema_migrations``（由 alembic 维护）
  不开 RLS（按 09 9.4.2 例外说明）

索引策略：

- 按 09 9.5 节：GIN（JSONB / tags）、trigram（name 模糊）、B-tree 复合索引
- 添加 ``pg_trgm`` 扩展以支持 templates.name trigram 索引
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, INET, UUID as PGUUID

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ===== 公共 helper =====


def _enable_rls(table_name: str) -> None:
    """启用 RLS + 创建 tenant_isolation policy.

    策略为 ``FOR ALL``：覆盖 SELECT/INSERT/UPDATE/DELETE。
    USING 表达式使用 ``current_setting('app.current_tenant', true)``，
    第二个参数 ``true`` 表示缺省时返回 NULL（不抛错），由 USING 的 IS NULL 比较分支放行。

    兼容官方模板等 ``tenant_id IS NULL`` 行：USING 允许 NULL 行通过（用于官方模板展示）。
    """
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {table_name}
            FOR ALL
            USING (
                tenant_id IS NULL
                OR tenant_id::text = current_setting('app.current_tenant', true)
                OR current_setting('app.current_tenant', true) IS NULL
            )
            WITH CHECK (
                tenant_id::text = current_setting('app.current_tenant', true)
                OR current_setting('app.current_tenant', true) IS NULL
            )
        """
    )


def _disable_rls(table_name: str) -> None:
    """删除 RLS policy + 关闭 RLS（downgrade 用）."""
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}")
    op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")


# ===== upgrade =====


def upgrade() -> None:
    """创建所有 21 张表 + 索引 + RLS."""
    # ---- 启用 pg_trgm 扩展（templates.name 模糊搜索需要） ----
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ---- 1. tenants ----
    op.create_table(
        "tenants",
        sa.Column("tenant_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("plan", sa.String(32), nullable=False, server_default=sa.text("'free'")),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("settings", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        comment="租户主表",
    )
    op.create_index("ix_tenants_status", "tenants", ["status"])

    # 注意：tenants 表自身不需要 RLS（应用层负责）

    # ---- 2. users ----
    op.create_table(
        "users",
        sa.Column("user_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("display_name", sa.String(128), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("locale", sa.String(16), nullable=True, server_default=sa.text("'zh-CN'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        comment="平台全局用户表",
    )
    # users 不带 tenant_id（用户跨租户），不开 RLS

    # ---- 3. tenant_members ----
    op.create_table(
        "tenant_members",
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", PGUUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("invited_by", PGUUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="租户成员关联",
    )
    op.create_index("ix_tenant_members_user", "tenant_members", ["user_id"])
    # tenant_members 不开 RLS（成员管理需跨租户查；service 层做权限控制）

    # ---- 4. user_invitations ----
    op.create_table(
        "user_invitations",
        sa.Column("invitation_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("token", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by", PGUUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="用户邀请记录",
    )
    op.create_index("ix_user_invitations_tenant_id", "user_invitations", ["tenant_id"])
    _enable_rls("user_invitations")

    # ---- 5. api_keys ----
    op.create_table(
        "api_keys",
        sa.Column("api_key_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", PGUUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("scopes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        comment="API 密钥元数据",
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    _enable_rls("api_keys")

    # ---- 9. templates (先建，workflow_templates 需要引用) ----
    # 注：迁移 09 给出的 workflow_templates 在 8 的位置，导致 FK 后向引用 templates.
    # 通过先建 templates 再 alter workflow_templates 的 FK 列解决。
    op.create_table(
        "templates",
        sa.Column("template_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("visibility", sa.String(32), nullable=False, server_default=sa.text("'tenant'")),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
            comment="标签数组",
        ),
        sa.Column("icon", sa.String(128), nullable=True),
        sa.Column("preview_image_path", sa.Text, nullable=True),
        sa.Column("use_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("rating_avg", sa.Numeric(3, 2), nullable=True),
        sa.Column("rating_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        comment="工作流模板",
    )
    op.create_index("ix_templates_category", "templates", ["category"])
    op.create_index("ix_templates_tenant_deleted", "templates", ["tenant_id", "deleted_at"])
    op.create_index(
        "ix_templates_tenant_active",
        "templates",
        ["tenant_id", "category", "visibility"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_templates_name_trgm",
        "templates",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    _enable_rls("templates")

    # ---- 6. workflows ----
    op.create_table(
        "workflows",
        sa.Column("workflow_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("current_version_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column("tags", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        comment="工作流主表",
    )
    op.create_index("ix_workflows_tenant_id", "workflows", ["tenant_id"])
    op.create_index(
        "ix_workflows_tenant_active",
        "workflows",
        ["tenant_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_workflows_tags",
        "workflows",
        ["tags"],
        postgresql_using="gin",
    )
    _enable_rls("workflows")

    # ---- 7. workflow_versions ----
    op.create_table(
        "workflow_versions",
        sa.Column("version_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workflow_id", PGUUID(as_uuid=True), sa.ForeignKey("workflows.workflow_id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("definition", JSONB, nullable=False),
        sa.Column("change_summary", sa.Text, nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="工作流版本历史",
    )
    op.create_index("ix_workflow_versions_workflow", "workflow_versions", ["workflow_id"])
    op.create_index(
        "ix_workflow_versions_definition",
        "workflow_versions",
        ["definition"],
        postgresql_using="gin",
    )
    op.create_unique_constraint(
        "uq_workflow_versions_wv", "workflow_versions", ["workflow_id", "version_number"]
    )

    # 追加 workflows.current_version_id FK（workflows 创建时 templates/workflow_versions 都不存在）
    op.create_foreign_key(
        "fk_workflows_current_version",
        "workflows",
        "workflow_versions",
        ["current_version_id"],
        ["version_id"],
        ondelete="SET NULL",
    )

    # ---- 8. workflow_templates (关联 workflow <-> template) ----
    op.create_table(
        "workflow_templates",
        sa.Column("workflow_id", PGUUID(as_uuid=True), sa.ForeignKey("workflows.workflow_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("template_id", PGUUID(as_uuid=True), sa.ForeignKey("templates.template_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_version_number", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="工作流与模板的多对多关联",
    )
    op.create_index("ix_workflow_templates_template", "workflow_templates", ["template_id"])

    # ---- 10. template_versions ----
    op.create_table(
        "template_versions",
        sa.Column("version_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("template_id", PGUUID(as_uuid=True), sa.ForeignKey("templates.template_id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("nodes", JSONB, nullable=False),
        sa.Column("edges", JSONB, nullable=False),
        sa.Column("default_params", JSONB, nullable=True),
        sa.Column("readme_md", sa.Text, nullable=True),
        sa.Column("change_summary", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="模板版本",
    )
    op.create_index("ix_template_versions_template", "template_versions", ["template_id"])
    op.create_unique_constraint(
        "uq_template_versions_t_vnum", "template_versions", ["template_id", "version_number"]
    )

    # ---- 11. template_ratings ----
    op.create_table(
        "template_ratings",
        sa.Column("rating_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_id", PGUUID(as_uuid=True), sa.ForeignKey("templates.template_id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", PGUUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="模板评分",
    )
    op.create_index("ix_template_ratings_template", "template_ratings", ["template_id"])
    op.create_index("ix_template_ratings_tenant_id", "template_ratings", ["tenant_id"])
    op.create_unique_constraint(
        "uq_template_ratings_user", "template_ratings", ["template_id", "user_id"]
    )
    op.create_check_constraint(
        "ck_template_ratings_range", "template_ratings", "rating >= 1 AND rating <= 5"
    )
    _enable_rls("template_ratings")

    # ---- 12. runs ----
    op.create_table(
        "runs",
        sa.Column("run_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("workflow_id", PGUUID(as_uuid=True), sa.ForeignKey("workflows.workflow_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("workflow_version_id", PGUUID(as_uuid=True), sa.ForeignKey("workflow_versions.version_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("workflow_version_number", sa.Integer, nullable=False),
        sa.Column("run_number", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("submitted_by", PGUUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Integer, nullable=True),
        sa.Column("inputs_snapshot", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metrics", JSONB, nullable=True),
        sa.Column("manifest", JSONB, nullable=True),
        sa.Column("error", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="工作流执行",
    )
    op.create_index("ix_runs_workflow_id", "runs", ["workflow_id"])
    op.create_index(
        "uq_runs_tenant_run_number", "runs", ["tenant_id", "run_number"], unique=True
    )
    op.create_index(
        "ix_runs_tenant_submitted",
        "runs",
        ["tenant_id", sa.text("submitted_at DESC")],
    )
    op.create_index(
        "ix_runs_tenant_status",
        "runs",
        ["tenant_id", "status", "submitted_at"],
    )
    op.create_index(
        "ix_runs_workflow",
        "runs",
        ["tenant_id", "workflow_id", "submitted_at"],
    )
    _enable_rls("runs")

    # ---- 13. node_executions ----
    op.create_table(
        "node_executions",
        sa.Column("node_exec_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_id", PGUUID(as_uuid=True), sa.ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(128), nullable=False),
        sa.Column("node_type", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("output_hash", sa.String(64), nullable=True),
        sa.Column("cached_from_run_id", PGUUID(as_uuid=True), sa.ForeignKey("runs.run_id", ondelete="SET NULL"), nullable=True),
        sa.Column("params", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("artifact_paths", JSONB, nullable=True),
        sa.Column("error", JSONB, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="节点执行记录",
    )
    op.create_index("ix_node_executions_run_node", "node_executions", ["run_id", "node_id"])
    op.create_index("ix_node_executions_tenant_id", "node_executions", ["tenant_id"])
    op.create_index(
        "ix_node_executions_status",
        "node_executions",
        ["tenant_id", "status", "queued_at"],
    )
    op.create_index(
        "ix_node_executions_cache",
        "node_executions",
        ["tenant_id", "node_type", "input_hash"],
    )
    _enable_rls("node_executions")

    # ---- 14. node_execution_logs ----
    op.create_table(
        "node_execution_logs",
        sa.Column("log_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("node_exec_id", PGUUID(as_uuid=True), sa.ForeignKey("node_executions.node_exec_id", ondelete="CASCADE"), nullable=False),
        sa.Column("stream", sa.String(16), nullable=False),
        sa.Column("line", sa.Text, nullable=False),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="节点执行日志（append-only）",
    )
    op.create_index("ix_node_execution_logs_logged", "node_execution_logs", ["node_exec_id", "logged_at"])
    op.create_index("ix_node_execution_logs_tenant_id", "node_execution_logs", ["tenant_id"])
    # append-only：DAL 层约束；不在 DB 加触发器
    _enable_rls("node_execution_logs")

    # ---- 15. node_artifacts ----
    op.create_table(
        "node_artifacts",
        sa.Column("artifact_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("node_exec_id", PGUUID(as_uuid=True), sa.ForeignKey("node_executions.node_exec_id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="节点级产物元数据",
    )
    op.create_index("ix_node_artifacts_node_exec", "node_artifacts", ["node_exec_id"])
    op.create_index("ix_node_artifacts_tenant_created", "node_artifacts", ["tenant_id", "created_at"])
    op.create_unique_constraint(
        "uq_node_artifact_dedup",
        "node_artifacts",
        ["node_exec_id", "artifact_type", "sha256"],
    )
    _enable_rls("node_artifacts")

    # ---- 16. run_artifacts ----
    op.create_table(
        "run_artifacts",
        sa.Column("artifact_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_id", PGUUID(as_uuid=True), sa.ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="Run 级产物聚合",
    )
    op.create_index("ix_run_artifacts_run", "run_artifacts", ["run_id"])
    op.create_index("ix_run_artifacts_tenant_created", "run_artifacts", ["tenant_id", "created_at"])
    _enable_rls("run_artifacts")

    # ---- 17. node_definitions ----
    op.create_table(
        "node_definitions",
        sa.Column("node_type", sa.String(128), primary_key=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("icon", sa.String(128), nullable=True),
        sa.Column("contract_version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("contract", JSONB, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="系统节点注册表（全局共享）",
    )
    op.create_index(
        "ix_node_definitions_category_enabled",
        "node_definitions",
        ["category", "enabled"],
    )
    # node_definitions 不开 RLS（全局共享）

    # ---- 18. custom_nodes ----
    op.create_table(
        "custom_nodes",
        sa.Column("custom_node_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("node_type", sa.String(128), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("visibility", sa.String(32), nullable=False, server_default=sa.text("'private'")),
        sa.Column("code", sa.Text, nullable=False),
        sa.Column("requirements", sa.Text, nullable=True),
        sa.Column("contract", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", PGUUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        comment="用户自定义节点",
    )
    op.create_index("ix_custom_nodes_tenant_id", "custom_nodes", ["tenant_id"])
    op.create_unique_constraint(
        "uq_custom_nodes_tenant_node_type",
        "custom_nodes",
        ["tenant_id", "node_type"],
    )
    op.create_index("ix_custom_nodes_visibility", "custom_nodes", ["tenant_id", "visibility"])
    _enable_rls("custom_nodes")

    # ---- 19. custom_node_versions ----
    op.create_table(
        "custom_node_versions",
        sa.Column("version_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("custom_node_id", PGUUID(as_uuid=True), sa.ForeignKey("custom_nodes.custom_node_id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("code", sa.Text, nullable=False),
        sa.Column("contract", JSONB, nullable=False),
        sa.Column("requirements", sa.Text, nullable=True),
        sa.Column("change_summary", sa.Text, nullable=True),
        sa.Column("created_by", PGUUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="自定义节点版本历史",
    )
    op.create_index("ix_custom_node_versions_node", "custom_node_versions", ["custom_node_id"])
    op.create_unique_constraint(
        "uq_custom_node_versions_cn_vnum",
        "custom_node_versions",
        ["custom_node_id", "version_number"],
    )

    # ---- 20. custom_node_test_runs ----
    op.create_table(
        "custom_node_test_runs",
        sa.Column("test_run_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version_id", PGUUID(as_uuid=True), sa.ForeignKey("custom_node_versions.version_id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("log", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggered_by", PGUUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="自定义节点测试运行",
    )
    op.create_index("ix_custom_node_test_runs_version", "custom_node_test_runs", ["version_id"])
    op.create_index("ix_custom_node_test_runs_tenant_id", "custom_node_test_runs", ["tenant_id"])
    _enable_rls("custom_node_test_runs")

    # ---- 21. audit_events ----
    op.create_table(
        "audit_events",
        sa.Column("event_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PGUUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", PGUUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("ip_address", INET, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        comment="审计事件",
    )
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index(
        "ix_audit_events_tenant_occurred",
        "audit_events",
        ["tenant_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_audit_events_user_occurred",
        "audit_events",
        ["user_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_audit_events_action",
        "audit_events",
        ["tenant_id", "action", "occurred_at"],
    )
    # audit_events 开启 RLS（同 tenant_id），但跨租户审计由 service 层切 role
    _enable_rls("audit_events")


# ===== downgrade =====


def downgrade() -> None:
    """按依赖反向顺序删除所有表 + 索引 + RLS."""
    # 先删除约束 / RLS 策略
    for table in (
        "audit_events",
        "custom_node_test_runs",
        "custom_nodes",
        "node_artifacts",
        "run_artifacts",
        "node_execution_logs",
        "node_executions",
        "runs",
        "template_ratings",
        "template_versions",
        "workflow_templates",
        "workflows",
        "workflow_versions",
        "templates",
        "api_keys",
        "user_invitations",
    ):
        _disable_rls(table)

    # 删除表（依赖反向）
    op.drop_table("audit_events")
    op.drop_table("custom_node_test_runs")
    op.drop_table("custom_node_versions")
    op.drop_table("custom_nodes")
    op.drop_table("node_definitions")
    op.drop_table("run_artifacts")
    op.drop_table("node_artifacts")
    op.drop_table("node_execution_logs")
    op.drop_table("node_executions")
    op.drop_table("runs")
    op.drop_table("template_ratings")
    op.drop_table("template_versions")
    op.drop_table("templates")
    op.drop_table("workflow_templates")
    # workflows.current_version_id FK 引用 workflow_versions，先删 fk + workflow_versions 用 fk
    op.drop_constraint("fk_workflows_current_version", "workflows", type_="foreignkey")
    op.drop_table("workflow_versions")
    op.drop_table("workflows")
    op.drop_table("api_keys")
    op.drop_table("user_invitations")
    op.drop_table("tenant_members")
    op.drop_table("users")
    op.drop_table("tenants")
