"""模板审核日志 — Phase 6 B31.

记录每次模板状态变更 (draft → pending → approved/rejected) 的审计追踪,
便于治理跨租户模板市场.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from hscredit_studio.core.database import Base
from hscredit_studio.models.base import TimestampMixin


class TemplateReviewLog(Base, TimestampMixin):
    """模板审核日志 (Phase 6 B31)."""

    __tablename__ = "template_review_logs"

    log_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("templates.template_id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
        comment="审核人 user_id (super_admin 或 tenant_admin)",
    )
    old_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    new_status: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    __table_args__ = (
        Index("ix_template_review_logs_template", "template_id"),
        Index("ix_template_review_logs_reviewer", "reviewer_id"),
    )


__all__ = ["TemplateReviewLog"]
