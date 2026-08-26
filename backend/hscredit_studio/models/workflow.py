"""工作流定义与版本模型.

按 09 第 9.3.2 节实现：

- :class:`Workflow` — 工作流主表（指向 current_version）
- :class:`WorkflowVersion` — 版本历史（DAG + 边 + 全局参数）
- :class:`WorkflowTemplate` — 工作流与模板的多对多关联表
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hscredit_studio.core.database import Base
from hscredit_studio.models.base import (
    ModelSerializerMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)


class Workflow(Base, TimestampMixin, SoftDeleteMixin, TenantMixin, ModelSerializerMixin):
    """工作流主表.

    通过 ``current_version_id`` 指向 ``workflow_versions`` 的一张记录；
    该字段由 service 层在新增版本后维护（DB 层用 FK NOT NULL）。
    """

    __tablename__ = "workflows"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="工作流名")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="当前 HEAD 版本 ID（service 层维护）",
    )
    tags: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        comment="标签数组（GIN 索引）",
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    # 关系
    versions: Mapped[list["WorkflowVersion"]] = relationship(
        "WorkflowVersion",
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowVersion.version_number",
    )

    __table_args__ = (
        # 软删除过滤索引：仅活跃工作流按租户索引
        Index(
            "ix_workflows_tenant_active",
            "tenant_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # tags GIN 索引
        Index(
            "ix_workflows_tags",
            "tenant_id",
            "tags",
            postgresql_using="gin",
        ),
    )


class WorkflowVersion(Base, TimestampMixin, ModelSerializerMixin):
    """工作流版本历史.

    ``version_number`` 在单个 workflow 内自增（service 层维护）；
    唯一约束 ``(workflow_id, version_number)``。
    """

    __tablename__ = "workflow_versions"

    version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflows.workflow_id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="workflow 内递增版本号（1, 2, 3, ...）",
    )
    definition: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="节点 DAG + 边 + 全局参数",
    )
    change_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="版本变更说明",
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    # 关系
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("workflow_id", "version_number", name="uq_workflow_versions_wv"),
        Index("ix_workflow_versions_workflow", "workflow_id"),
        # definition 字段 GIN 索引，方便按节点类型、内容查询
        Index(
            "ix_workflow_versions_definition",
            "definition",
            postgresql_using="gin",
        ),
    )


class WorkflowTemplate(Base, TimestampMixin):
    """工作流与模板的多对多关联表.

    一条记录代表"该 workflow 由该 template 的某版本实例化而来"，
    通常一条 workflow 对应一条记录（如由模板新建）。
    """

    __tablename__ = "workflow_templates"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflows.workflow_id", ondelete="CASCADE"),
        primary_key=True,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("templates.template_id", ondelete="RESTRICT"),
        nullable=False,
    )
    template_version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="使用的模板版本号",
    )

    __table_args__ = (
        Index("ix_workflow_templates_template", "template_id"),
    )


__all__ = [
    "Workflow",
    "WorkflowVersion",
    "WorkflowTemplate",
]
