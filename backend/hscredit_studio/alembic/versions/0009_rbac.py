"""Phase 6 B28 — RBAC 细化迁移.

依据 docs/ROADMAP.md Phase 6 B28:

> 角色: super_admin / tenant_admin / analyst / viewer 四级
> 资源权限矩阵: Workflow / Run / Model / Template / Billing 各自 read/write/admin
> 后端中间件强制检查

本迁移:

- 新增 :class:`RolePolicy` 表 (资源 × 动作矩阵的可配置覆盖).
- 新增 :class:`UserRoleAudit` 表 (角色变更审计, PIPL 合规留痕).
- 扩展 ``users.is_super_admin`` 标记平台超管 (跨租户权限).

注:
- 角色枚举值在代码层通过 ``services.rbac.Role`` 集中定义.
- 本迁移仅添加可配置覆盖与审计; 不动 ``tenant_members.role`` 既有值.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0009_rbac"
down_revision: str | None = "0008_alert"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ===== 1. users 表新增 is_super_admin 列 =====
    op.add_column(
        "users",
        sa.Column(
            "is_super_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="平台超管标记 (跨租户访问)",
        ),
    )
    op.create_index(
        "ix_users_super_admin",
        "users",
        ["is_super_admin"],
        unique=False,
        postgresql_where=sa.text("is_super_admin = true"),
    )

    # ===== 2. role_policies 表 =====
    op.create_table(
        "role_policies",
        sa.Column("policy_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("role", sa.String(length=32), nullable=False, comment="角色: super_admin/tenant_admin/analyst/viewer"),
        sa.Column("resource", sa.String(length=32), nullable=False, comment="资源: workflow/run/model/template/billing"),
        sa.Column("allowed_action", sa.String(length=16), nullable=False, comment="read/write/admin"),
        sa.Column("tenant_id", PGUUID(as_uuid=True), nullable=True, comment="NULL=全局, 否则=租户级覆盖"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("comment", sa.String(length=256), nullable=True),
        sa.UniqueConstraint(
            "role",
            "resource",
            "tenant_id",
            name="uq_role_policies_role_resource_tenant",
        ),
    )
    op.create_index("ix_role_policies_role", "role_policies", ["role"])

    # ===== 3. user_role_audit 表 =====
    op.create_table(
        "user_role_audit",
        sa.Column("audit_id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("tenant_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("user_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("old_role", sa.String(length=32), nullable=True, comment="变更前角色 (NULL=新增)"),
        sa.Column("new_role", sa.String(length=32), nullable=False, comment="变更后角色"),
        sa.Column("changed_by", PGUUID(as_uuid=True), nullable=False, comment="变更发起人 user_id"),
        sa.Column("reason", sa.String(length=512), nullable=True, comment="变更原因"),
        sa.Column("extra", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_user_role_audit_user", "user_role_audit", ["user_id"])
    op.create_index("ix_user_role_audit_tenant", "user_role_audit", ["tenant_id"])
    op.create_index("ix_user_role_audit_created", "user_role_audit", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_role_audit_created", table_name="user_role_audit")
    op.drop_index("ix_user_role_audit_tenant", table_name="user_role_audit")
    op.drop_index("ix_user_role_audit_user", table_name="user_role_audit")
    op.drop_table("user_role_audit")

    op.drop_index("ix_role_policies_role", table_name="role_policies")
    op.drop_table("role_policies")

    op.drop_index("ix_users_super_admin", table_name="users")
    op.drop_column("users", "is_super_admin")
