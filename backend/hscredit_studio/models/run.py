"""执行（Run）相关模型.

按 09 第 9.3.3 节实现：

- :class:`Run` — 工作流执行实例
- :class:`NodeExecution` — 单节点执行记录
- :class:`NodeExecutionLog` — 节点日志（append-only）
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hscredit_studio.core.database import Base
from hscredit_studio.models.base import (
    ModelSerializerMixin,
    TenantMixin,
    TimestampMixin,
)

RUN_STATUS_VALUES = (
    "pending",
    "queued",
    "running",
    "success",
    "failed",
    "cancelled",
    "cached",
)
"""Run.status 枚举值."""

NODE_STATUS_VALUES = (
    "queued",
    "running",
    "cached_hit",
    "success",
    "failed_retry",
    "failed",
    "cancelled",
)
"""NodeExecution.status 枚举值."""

LOG_STREAM_VALUES = ("stdout", "stderr", "system")
"""NodeExecutionLog.stream 枚举值."""


class Run(Base, TimestampMixin, TenantMixin, ModelSerializerMixin):
    """工作流每次执行（一次工作流提交 = 一条 Run）.

    ``run_number`` 在租户内自增，用作业务键；通过 UNIQUE 索引保证。
    ``workflow_version_id`` 指向快照时的版本（不可变）。
    """

    __tablename__ = "runs"

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflows.workflow_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workflow_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_versions.version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    workflow_version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="工作流版本号（冗余字段，UI 显示用）",
    )
    run_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="租户内自增业务编号（如 #0042）",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment=f"运行状态，取值 {RUN_STATUS_VALUES}",
    )
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=text("now()"),
        comment="提交时间",
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="运行时长（秒）；可由 service 层用 finished - started 计算",
    )
    inputs_snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="数据快照引用 + 哈希",
    )
    metrics: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="训练指标（KS / AUC / IV）",
    )
    manifest: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="完整 run manifest（见 06-non-functional 6.5）",
    )
    error: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="失败时的错误信息",
    )

    # 关系
    node_executions: Mapped[list[NodeExecution]] = relationship(
        "NodeExecution",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="NodeExecution.created_at",
        # node_executions 与 runs 之间有两个 FK（run_id / cached_from_run_id），
        # 必须显式指定以避免 AmbiguousForeignKeysError
        foreign_keys="NodeExecution.run_id",
    )

    __table_args__ = (
        # 租户内 run_number 业务键唯一
        Index(
            "uq_runs_tenant_run_number",
            "tenant_id",
            "run_number",
            unique=True,
        ),
        # 列表查询：按租户 + 提交时间倒序
        Index(
            "ix_runs_tenant_submitted",
            "tenant_id",
            "submitted_at",
        ),
        # 列表按状态过滤
        Index(
            "ix_runs_tenant_status",
            "tenant_id",
            "status",
            "submitted_at",
        ),
        # 按 workflow 查询历史
        Index(
            "ix_runs_workflow",
            "tenant_id",
            "workflow_id",
            "submitted_at",
        ),
    )


class NodeExecution(Base, TimestampMixin, TenantMixin, ModelSerializerMixin):
    """单个节点执行记录.

    包含输入哈希、输出哈希、产物路径、重试次数等。
    ``cached_from_run_id`` 实现跨 run 缓存命中。
    """

    __tablename__ = "node_executions"

    node_exec_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="用户在工作流内定义的节点 ID（unique per workflow）",
    )
    node_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="注册表里的节点类型",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'queued'"),
        comment=f"节点执行状态，取值 {NODE_STATUS_VALUES}",
    )
    input_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="输入数据的 sha256 哈希",
    )
    output_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="输出数据的 sha256 哈希",
    )
    cached_from_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("runs.run_id", ondelete="SET NULL"),
        nullable=True,
        comment="缓存命中来源 run",
    )
    params: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="参数快照",
    )
    artifact_paths: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="产物路径列表 / 元数据",
    )
    error: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="失败错误")
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="已重试次数",
    )
    queued_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 关系
    run: Mapped[Run] = relationship(
        "Run",
        back_populates="node_executions",
        foreign_keys=[run_id],
    )
    logs: Mapped[list[NodeExecutionLog]] = relationship(
        "NodeExecutionLog",
        back_populates="node_execution",
        cascade="all, delete-orphan",
        order_by="NodeExecutionLog.logged_at",
    )

    __table_args__ = (
        # 同一 run 内按 node_id 索引
        Index("ix_node_executions_run_node", "run_id", "node_id"),
        # 调度器常用：按 tenant + 状态 + queued_at
        Index("ix_node_executions_status", "tenant_id", "status", "queued_at"),
        # 缓存命中查询：按 tenant + node_type + input_hash
        Index(
            "ix_node_executions_cache",
            "tenant_id",
            "node_type",
            "input_hash",
        ),
    )


class NodeExecutionLog(Base, ModelSerializerMixin):
    """节点执行日志（append-only）.

    BIGSERIAL PK 适合高吞吐写入；按 ``logged_at`` 月分区，
    保留 30 天后归档/删除。
    """

    __tablename__ = "node_execution_logs"

    log_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="BIGSERIAL PK",
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    node_exec_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("node_executions.node_exec_id", ondelete="CASCADE"),
        nullable=False,
    )
    stream: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=f"日志流，取值 {LOG_STREAM_VALUES}",
    )
    line: Mapped[str] = mapped_column(Text, nullable=False, comment="一行日志内容")
    logged_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=text("now()"),
    )

    # 关系
    node_execution: Mapped[NodeExecution] = relationship(
        "NodeExecution",
        back_populates="logs",
    )

    __table_args__ = (Index("ix_node_execution_logs_logged", "node_exec_id", "logged_at"),)


__all__ = [
    "LOG_STREAM_VALUES",
    "NODE_STATUS_VALUES",
    "RUN_STATUS_VALUES",
    "NodeExecution",
    "NodeExecutionLog",
    "Run",
]
