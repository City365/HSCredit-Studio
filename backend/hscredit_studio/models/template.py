"""模板（template）相关模型.

按 09 第 9.3.6 节实现：

- :class:`Template` — 模板主表（官方模板 ``tenant_id`` 为 NULL）
- :class:`TemplateVersion` — 模板版本（节点 + 边 + 默认参数）
- :class:`TemplateRating` — 模板评分
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hscredit_studio.core.database import Base
from hscredit_studio.models.base import (
    ModelSerializerMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)


# 09 中包含 ``private/team/tenant/official`` 四档；本项目支持前三档 + ``public``
# 平台上架的官方模板枚举（OFFICIAL_TENANT_VALUES 实际为 NULL 表示平台官方）。
TEMPLATE_VISIBILITY_VALUES = ("private", "tenant", "public")
"""Template.visibility 枚举值.

注：09 文档使用 ``official``（tenant_id=NULL），此处保持向后兼容，
所有 tenant_id IS NULL 的行视为 ``official``；业务代码会跳过此值。
"""


class Template(Base, TimestampMixin, SoftDeleteMixin, TenantMixin, ModelSerializerMixin):
    """模板主表.

    ``tenant_id`` 为 NULL 时表示平台官方模板，需要 NULL 也参与 RLS 验证，
    所以 RLS policy 应用 ``tenant_id IS NULL`` 旁路或专用 policy。
    """

    __tablename__ = "templates"

    template_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="模板分类（评分卡建模 / 监控 / 模型部署）",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="模板名")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'tenant'"),
        comment=f"可见性，取值 {TEMPLATE_VISIBILITY_VALUES}",
    )
    tags: Mapped[list[str]] = mapped_column(
        "tags",
        ARRAY(String),
        nullable=False,
        server_default=text("'{}'::text[]"),
        comment="标签数组",
    )
    icon: Mapped[str | None] = mapped_column(String(128), nullable=True)
    preview_image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    use_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="被实例化次数",
    )
    rating_avg: Mapped[float | None] = mapped_column(
        Numeric(3, 2),
        nullable=True,
        comment="缓存的均分（1.00 - 5.00）",
    )
    rating_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="评分人数",
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    # 关系
    versions: Mapped[list["TemplateVersion"]] = relationship(
        "TemplateVersion",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateVersion.version_number",
    )
    ratings: Mapped[list["TemplateRating"]] = relationship(
        "TemplateRating",
        back_populates="template",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # 软删除过滤索引
        Index(
            "ix_templates_tenant_active",
            "tenant_id",
            "category",
            "visibility",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # name 模糊查询：依赖 pg_trgm 扩展（迁移中 CREATE EXTENSION）
        Index(
            "ix_templates_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index("ix_templates_tenant_deleted", "tenant_id", "deleted_at"),
    )


class TemplateVersion(Base, TimestampMixin, ModelSerializerMixin):
    """模板版本（节点 + 边 + 默认参数）."""

    __tablename__ = "template_versions"

    version_id: Mapped[uuid.UUID] = mapped_column(
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
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    nodes: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="节点列表（拓扑）",
    )
    edges: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="边列表（拓扑）",
    )
    default_params: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="节点默认参数表",
    )
    readme_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 关系
    template: Mapped["Template"] = relationship("Template", back_populates="versions")

    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "version_number",
            name="uq_template_versions_t_vnum",
        ),
        Index("ix_template_versions_template", "template_id"),
    )


class TemplateRating(Base, TimestampMixin, TenantMixin, ModelSerializerMixin):
    """模板评分（1-5 星 + 评论）."""

    __tablename__ = "template_ratings"

    rating_id: Mapped[uuid.UUID] = mapped_column(
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
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    rating: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="1-5 整数评分",
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 关系
    template: Mapped["Template"] = relationship("Template", back_populates="ratings")

    __table_args__ = (
        # 同一用户对同一模板只能评分一次
        UniqueConstraint(
            "template_id",
            "user_id",
            name="uq_template_ratings_user",
        ),
        CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_template_ratings_range",
        ),
        Index("ix_template_ratings_template", "template_id"),
    )


__all__ = [
    "TEMPLATE_VISIBILITY_VALUES",
    "Template",
    "TemplateVersion",
    "TemplateRating",
]
