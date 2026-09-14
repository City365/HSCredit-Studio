"""节点定义与自定义节点模型.

按 09 第 9.3.5 节实现 + Phase 6 B36 节点可插拔扩展:

- :class:`NodeDefinition` — 全局系统节点注册表 (扩展: is_custom / owner_tenant_id / source / meta_editable)
- :class:`CustomNode` — 用户自定义节点 (扩展: enabled / icon / description / category / 当前版本/试运行统计/编辑锁)
- :class:`CustomNodeVersion` — 自定义节点版本历史
- :class:`CustomNodeTestRun` — 自定义节点测试运行
- :class:`NodeDefinitionDraft` — 编辑草稿 (Phase 6 B36 新增)
- :class:`NodeDefinitionLock` — 编辑锁 (Phase 6 B36 新增)
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
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

DRAFT_VALIDATION_STATUSES = ("draft", "validating", "valid", "invalid")
"""NodeDefinitionDraft.validation_status 枚举值."""


class NodeDefinition(Base, TimestampMixin, ModelSerializerMixin):
    """节点注册表 — 合并系统节点 + 自定义节点 (Phase 6 B36).

    启动时由 NodeRegistry 加载 hscredit 已注册节点 + 加载 DB 中的自定义节点,
    合并写入此表 (缓存). ``contract`` 字段保存完整 Pydantic contract 的 JSON 序列化.

    区分字段:
    - ``is_custom=False`` + ``owner_tenant_id IS NULL``: 系统节点
    - ``is_custom=True`` + ``owner_tenant_id=<uuid>``: 自定义节点
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

    # ========== Phase 6 B36 扩展 ==========
    is_custom: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        comment="区分系统节点 (false) vs 自定义节点 (true)",
    )
    owner_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=True,
        comment="自定义节点所属租户 (NULL = 系统节点)",
    )
    source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'system'"),
        comment="节点来源: 'system' / 'custom'",
    )
    meta_editable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        comment="元数据 (name/desc/icon) 是否可被管理员编辑",
    )

    __table_args__ = (
        Index("ix_node_definitions_category_enabled", "category", "enabled"),
        Index("ix_node_definitions_tenant", "owner_tenant_id"),
        Index("ix_node_definitions_custom_enabled", "is_custom", "enabled"),
        Index("ix_node_definitions_source", "source"),
    )


class CustomNode(Base, TimestampMixin, SoftDeleteMixin, TenantMixin, ModelSerializerMixin):
    """用户自定义节点 (Phase 6 B36 增强).

    ``visibility`` 控制可见范围：

    - ``private``：仅创建者
    - ``tenant``：同租户成员
    - ``public``：平台公开（需审批）

    Phase 6 B36 扩展:
    - ``enabled``: 启停开关
    - ``icon/description/category``: 元数据
    - ``current_version_number``: 当前激活版本 (冗余)
    - ``last_test_run_at/test_run_count``: 试运行统计
    - ``locked_by/locked_at``: 编辑锁 (软锁, 详见 NodeDefinitionLock)
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

    # ========== Phase 6 B36 扩展字段 ==========
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        comment="启停控制 (供管理页面开关)",
    )
    icon: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="图标 (emoji)")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="节点描述")
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'特征工程'"),
        comment="节点分类",
    )
    current_version_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="当前激活版本号 (冗余)",
    )
    last_test_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最后一次试运行时间",
    )
    test_run_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="试运行总次数",
    )
    locked_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        comment="当前编辑锁持有者",
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="编辑锁获取时间",
    )

    # 关系
    versions: Mapped[list[CustomNodeVersion]] = relationship(
        "CustomNodeVersion",
        back_populates="custom_node",
        cascade="all, delete-orphan",
        order_by="CustomNodeVersion.version_number",
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "node_type",
            name="uq_custom_nodes_tenant_node_type",
        ),
        Index("ix_custom_nodes_visibility", "tenant_id", "visibility"),
        Index("ix_custom_nodes_enabled", "enabled"),
        Index("ix_custom_nodes_tenant_enabled", "tenant_id", "enabled"),
        Index("ix_custom_nodes_category", "tenant_id", "category"),
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
    custom_node: Mapped[CustomNode] = relationship(
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

    在 Phase 6 沙箱中执行测试用；这里仅存元数据。

    注意: 实际节点归属通过 ``version_id → custom_node_versions.custom_node_id`` 反查,
    本表不直接存 ``custom_node_id`` 字段 (避免冗余).
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

    __table_args__ = (Index("ix_custom_node_test_runs_version", "version_id"),)


# ========== Phase 6 B36 新增模型 ==========


class NodeDefinitionDraft(Base, TimestampMixin, ModelSerializerMixin):
    """节点编辑草稿 (Phase 6 B36 新增).

    用户在编辑节点时, 频繁保存到 draft 而非新版本. 避免版本历史膨胀.
    草稿可丢弃, 不污染版本链. 每个 custom_node 只有一个活跃 draft.

    包含:
    - 当前编辑中的 code + contract
    - AST 反推的 contract_preview (缓存)
    - 校验状态 (draft/validating/valid/invalid) + issues
    """

    __tablename__ = "node_definition_drafts"

    draft_id: Mapped[uuid.UUID] = mapped_column(
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
    draft_code: Mapped[str] = mapped_column(Text, nullable=False, comment="草稿 Python 源码")
    draft_contract: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="草稿 contract (用户编辑中)",
    )
    contract_preview: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="AST 反推的 contract 预览 (缓存)",
    )
    validation_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'draft'"),
        comment=f"校验状态, 取值 {DRAFT_VALIDATION_STATUSES}",
    )
    validation_issues: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="校验 issues 列表 (含行号/规则/消息)",
    )
    last_validation_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最后一次校验时间",
    )
    locked_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        comment="草稿锁定人 (与编辑锁同步)",
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="草稿锁定时间",
    )

    __table_args__ = (
        UniqueConstraint("custom_node_id", name="uq_drafts_custom_node"),
        Index("ix_drafts_validation_status", "validation_status"),
    )


class NodeDefinitionLock(Base, TimestampMixin, ModelSerializerMixin):
    """节点编辑锁 (Phase 6 B36 新增).

    防止多人同时编辑同一节点导致覆盖. TTL + 心跳续期.
    Celery beat 定时清理过期锁.

    Lock 机制:
    - 进入编辑页 → POST /lock (TTL = 5 分钟)
    - 心跳每 2 分钟 → POST /lock/heartbeat (续期)
    - 关闭页面 → DELETE /lock (主动释放)
    - TTL 过期 → Celery beat 清理
    """

    __tablename__ = "node_definition_locks"

    lock_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    node_type: Mapped[str] = mapped_column(String(128), nullable=False, comment="节点类型")
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    locked_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        comment="锁持有者",
    )
    locked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        comment="锁获取时间",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="过期时间 (默认 5 分钟后)",
    )

    __table_args__ = (
        UniqueConstraint("node_type", "tenant_id", name="uq_node_locks_type_tenant"),
        Index("ix_node_locks_expires", "expires_at"),
    )


class NodeResourceUsage(Base, TimestampMixin, TenantMixin):
    """节点沙箱执行资源消耗记录 (Phase 3 B17).

每次节点执行 (NodeExecution) 后, 由 :class:`SubprocessSandbox` 写入:
    - ``cpu_seconds``: 用户态 CPU 时间 (跨平台可用 resource.getrusage / 子进程计时)
    - ``mem_peak_mb``: 峰值常驻内存 (MB; subprocess 后端在 Windows 上不支持, 记 0)
    - ``duration_ms``: 端到端耗时 (毫秒, 主进程计时)
    - ``sandbox_backend``: ``subprocess / docker / kubernetes`` (供计费分档)
    - ``status``: ``success / failed / timeout / oom``

供:
    - Phase 4 计费模块 (用量聚合)
    - Phase 5 监控大屏 (节点资源告警)
    - 租户自助用量查询
    """

    __tablename__ = "node_resource_usage"

    usage_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_uuid()"),
    )
    node_exec_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("node_executions.node_exec_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="关联 NodeExecution (1:1)",
    )
    node_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="节点类型 (e.g. csv_ingest)",
    )
    cpu_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("0"),
        comment="CPU 时间 (秒)",
    )
    mem_peak_mb: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("0"),
        comment="峰值 RSS (MB; 0 表示不支持)",
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="端到端耗时 (毫秒)",
    )
    sandbox_backend: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'subprocess'"),
        comment="沙箱后端: subprocess / docker / kubernetes",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'success'"),
        comment="执行结果: success / failed / timeout / oom",
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("now()"),
        comment="资源采集时刻",
    )

    __table_args__ = (
        Index("ix_node_resource_usage_tenant", "tenant_id"),
        Index("ix_node_resource_usage_node_type", "node_type"),
        Index("ix_node_resource_usage_captured_at", "captured_at"),
    )


__all__ = [
    "CUSTOM_NODE_TEST_RUN_STATUS_VALUES",
    "DRAFT_VALIDATION_STATUSES",
    "VISIBILITY_VALUES",
    "CustomNode",
    "CustomNodeTestRun",
    "CustomNodeVersion",
    "NodeDefinition",
    "NodeDefinitionDraft",
    "NodeDefinitionLock",
    "NodeResourceUsage",
]
