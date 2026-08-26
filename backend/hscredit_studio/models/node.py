"""节点定义与自定义节点模型.

按 09 第 9.3.5 节实现：

- :class:`NodeDefinition` — 全局系统节点注册表
- :class:`CustomNode` — 用户自定义节点
- :class:`CustomNodeVersion` — 自定义节点版本
- :class:`CustomNodeTestRun` — 自定义节点测试运行
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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


VISIBILITY_VALUES = ("private", "tenant", "public")
"""CustomNode.visibility 枚举值."""

CUSTOM_NODE_TEST_RUN_STATUS_VALUES = ("queued", "running", "success", "failed", "cancelled")
"""CustomNodeTestRun.status 枚举值."""


class NodeDefinition(Base, TimestampMixin, ModelSerializerMixin):
    """系统节点注册表（全局共享，无 tenant_id）.

    启动时由 NodeRegistry 加载 hscredit 已注册节点，并写入此表（缓存）。
    ``contract`` 字段保存完整 Pydantic contract 的 JSON 序列化。
    """

    __tablename__ = "node_definitions"

    node_type: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
        comment="节点类型唯一标识（如 optimal_binning_chi）",
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="节点分类（如 data_input / binning / encoding）",
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="中文显示名")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    icon: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="图标 URL 或名称")
    contract_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
        comment="contract schema 版本号",
    )
    contract: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="完整 Pydantic contract 序列化（inputs/outputs/cache）",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        comment="是否在 UI 中启用",
    )

    __table_args__ = (
        Index("ix_node_definitions_category_enabled", "category", "enabled"),
    )


class CustomNode(Base, TimestampMixin, SoftDeleteMixin, TenantMixin, ModelSerializerMixin):
    """用户自定义节点.

    ``visibility`` 控制可见范围：

    - ``private``：仅创建者
    - ``tenant``：同租户成员
    - ``public``：平台公开（需审批）
    """

    __tablename__ = "custom_nodes"

    custom_node_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    node_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="节点类型唯一标识（per-tenant 唯一）",
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="中文显示名")
    visibility: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'private'"),
        comment=f"可见性，取值 {VISIBILITY_VALUES}",
    )
    code: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="最新版本 Python 源码",
    )
    requirements: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="requirements.txt 内容",
    )
    contract: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="当前版本的 contract（冗余 service 层查不到时）",
    )
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True, comment="公开审批通过时间")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    # 关系
    versions: Mapped[list["CustomNodeVersion"]] = relationship(
        "CustomNodeVersion",
        back_populates="custom_node",
        cascade="all, delete-orphan",
        order_by="CustomNodeVersion.version_number",
    )

    __table_args__ = (
        # per-tenant node_type 唯一（不含已删除）
        UniqueConstraint(
            "tenant_id",
            "node_type",
            name="uq_custom_nodes_tenant_node_type",
        ),
        Index("ix_custom_nodes_visibility", "tenant_id", "visibility"),
    )


class CustomNodeVersion(Base, TimestampMixin, ModelSerializerMixin):
    """自定义节点版本历史.

    ``version_number`` 在 custom_node 内递增。
    """

    __tablename__ = "custom_node_versions"

    version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    custom_node_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("custom_nodes.custom_node_id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False, comment="Python 源码")
    contract: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="inputs/outputs/cache 配置",
    )
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True, comment="依赖白名单")
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    # 关系
    custom_node: Mapped["CustomNode"] = relationship(
        "CustomNode",
        back_populates="versions",
    )

    __table_args__ = (
        UniqueConstraint(
            "custom_node_id",
            "version_number",
            name="uq_custom_node_versions_cn_vnum",
        ),
        Index("ix_custom_node_versions_node", "custom_node_id"),
    )


class CustomNodeTestRun(Base, TimestampMixin, TenantMixin, ModelSerializerMixin):
    """自定义节点测试运行记录.

    在 Phase 3 沙箱中执行测试用；这里仅存元数据。
    """

    __tablename__ = "custom_node_test_runs"

    test_run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("custom_node_versions.version_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'queued'"),
        comment=f"测试状态，取值 {CUSTOM_NODE_TEST_RUN_STATUS_VALUES}",
    )
    log: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="完整测试日志（也可走 minio）",
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_custom_node_test_runs_version", "version_id"),
    )


__all__ = [
    "VISIBILITY_VALUES",
    "CUSTOM_NODE_TEST_RUN_STATUS_VALUES",
    "NodeDefinition",
    "CustomNode",
    "CustomNodeVersion",
    "CustomNodeTestRun",
]
