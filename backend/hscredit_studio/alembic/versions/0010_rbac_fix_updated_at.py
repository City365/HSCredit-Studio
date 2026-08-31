"""Phase 6 B28 fix — user_role_audit 加 updated_at 列.

TimestampMixin 期待 updated_at 但原 0009_rbac 未声明.

实际: 0009 修复时已直接包含 updated_at (线上修复), 0010 已变为 no-op.
本迁移保留以维持迁移链顺序, 不再重复添加列.
"""
from __future__ import annotations

from collections.abc import Sequence

revision: str = "0010_rbac_fix_updated_at"
down_revision: str | None = "0009_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # user_role_audit.updated_at 已在 0009 中声明 (线上修复合并), 此处不再重复添加.
    pass


def downgrade() -> None:
    # 历史列定义: 不删,避免破坏线上数据.
    pass
