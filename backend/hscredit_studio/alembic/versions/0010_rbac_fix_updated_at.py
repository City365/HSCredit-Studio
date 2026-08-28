"""Phase 6 B28 fix — user_role_audit 加 updated_at 列.

TimestampMixin 期待 updated_at 但原 0009_rbac 未声明.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_rbac_fix_updated_at"
down_revision: str | None = "0009_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_role_audit",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("user_role_audit", "updated_at")
