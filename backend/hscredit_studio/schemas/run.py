"""Run 与节点执行相关 schema.

工作流执行（Run）、节点执行（NodeExecution）、产物（Artifact）的请求/响应结构。

状态机（与 ORM 中的 ``RUN_STATUS_VALUES`` / ``NODE_STATUS_VALUES`` 对齐）：

- Run: pending → queued → running → success / failed / cancelled；cached 为
  跨 run 缓存命中后的特殊终态。
- NodeExecution: pending → running → success / failed / retrying / skipped；
  cached 为缓存命中。

设计要点：
- 列表项与详情分离：``*ListItem`` 精简字段；``*Response`` 携带完整 payload。
- 时间字段一律 ISO-8601 字符串，由 Pydantic 自动序列化。
- ``metrics`` / ``manifest`` / ``error`` / ``inputs_snapshot`` 等 JSONB 字段
  使用 ``dict[str, Any]`` 类型，序列化时直接展开。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hscredit_studio.schemas.common import IDSchema, TimestampedSchema

# ===== 状态枚举（与 ORM 常量字符串对齐） =====

RunStatus = Literal[
    "pending",
    "queued",
    "running",
    "cached",
    "success",
    "failed",
    "cancelled",
    "retrying",
]
"""Run.status 枚举.

注：ORM 端 ``RUN_STATUS_VALUES`` 未包含 ``pending`` / ``retrying``，
这两个值由 service 层写入用于 UI 表达（前置/重试中的状态）；
此处保留以便 API 直接覆盖。
"""

NodeExecutionStatus = Literal[
    "pending",
    "queued",
    "running",
    "cached",
    "cached_hit",
    "success",
    "failed",
    "failed_retry",
    "retrying",
    "skipped",
]
"""NodeExecution.status 枚举."""

ArtifactType = Literal[
    "parquet",
    "excel",
    "pmml",
    "json",
    "png",
    "pdf",
    "log",
    "pickle",
    # 机器学习模型工件（ORM 端 ``NODE_ARTIFACT_TYPE_VALUES``）。
    # 这些通常用 pickle 通道处理；扩展到 Literal 便于前端按类型着色。
    "model",
    "binner",
    "scorecard",
]
"""Artifact 类型枚举（含 UI 下载视图所需的扩展类型）.

注：ORM 端 ``NODE_ARTIFACT_TYPE_VALUES`` 与前端 Literal 对齐；新类型须三处同步
（ORM 常量 / schema Literal / 前端 ``ArtifactType``）。
"""


# ===== Run =====


class RunSubmitRequest(BaseModel):
    """提交 Run 请求体.

    Attributes
    ----------
    workflow_version_id:
        使用的 workflow version（不指定则用 current_version）。
    inputs_snapshot:
        输入数据快照（文件路径 / 引用 / 哈希等），由 service 层写入。
    priority:
        调度优先级（1=最高，10=最低；默认 5）。
    notes:
        备注（可选，<= 500 字符）。
    """

    workflow_version_id: UUID | None = Field(
        default=None,
        description="工作流版本 UUID（默认使用 HEAD 版本）",
    )
    inputs_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        description="输入快照（路径 / 引用 / 哈希）",
    )
    priority: int = Field(default=5, ge=1, le=10, description="调度优先级（1-10）")
    notes: str | None = Field(default=None, max_length=500, description="备注")


class RunListItem(IDSchema, TimestampedSchema):
    """Run 列表项（精简字段）.

    Attributes
    ----------
    workflow_id:
        所属工作流 UUID。
    workflow_version_id:
        使用的版本 UUID。
    run_number:
        租户内自增业务编号（如 ``#0042``）。
    status:
        运行状态。
    submitted_by:
        提交者 UUID。
    submitted_at:
        提交时间。
    started_at:
        实际启动时间。
    finished_at:
        结束时间。
    duration_seconds:
        运行时长（秒；``finished - started``）。
    progress:
        进度（0-1）。
    error_summary:
        失败摘要（中文）。
    """

    workflow_id: UUID = Field(..., description="所属工作流 UUID")
    workflow_version_id: UUID = Field(..., description="版本 UUID")
    run_number: int = Field(..., ge=1, description="租户内自增编号")
    status: RunStatus = Field(..., description="运行状态")
    submitted_by: UUID | None = Field(default=None, description="提交者 UUID")
    submitted_at: datetime = Field(..., description="提交时间")
    started_at: datetime | None = Field(default=None, description="启动时间")
    finished_at: datetime | None = Field(default=None, description="结束时间")
    duration_seconds: float | None = Field(default=None, ge=0, description="运行时长（秒）")
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="进度（0-1）")
    error_summary: str | None = Field(default=None, description="失败摘要（中文）")


class RunResponse(RunListItem):
    """Run 详情响应（完整字段）.

    Attributes
    ----------
    inputs_snapshot:
        完整输入快照。
    metrics:
        运行级指标（如 KS / AUC / IV）。
    manifest:
        完整 run manifest（执行计划、依赖、产物清单）。
    error:
        失败错误结构（code / message / details）。
    node_executions_count:
        关联的节点执行记录数。
    """

    inputs_snapshot: dict[str, Any] = Field(default_factory=dict, description="输入快照")
    metrics: dict[str, Any] = Field(default_factory=dict, description="运行级指标")
    manifest: dict[str, Any] = Field(default_factory=dict, description="run manifest")
    error: dict[str, Any] | None = Field(default=None, description="失败错误")
    node_executions_count: int = Field(default=0, ge=0, description="节点执行记录数")


# ===== NodeExecution =====


class NodeExecutionListItem(IDSchema):
    """节点执行列表项.

    Attributes
    ----------
    run_id:
        所属 Run UUID。
    node_id:
        工作流内节点 ID（与 :class:`NodeDef.id` 对齐）。
    node_type:
        节点类型。
    status:
        节点执行状态。
    retry_count:
        已重试次数。
    started_at:
        实际启动时间。
    finished_at:
        结束时间。
    duration_seconds:
        运行时长（秒）。
    cached_from_run_id:
        缓存命中的来源 Run UUID（NULL 表示非缓存命中）。
    """

    run_id: UUID = Field(..., description="所属 Run UUID")
    node_id: str = Field(..., description="节点 ID")
    node_type: str = Field(..., description="节点类型")
    status: NodeExecutionStatus = Field(..., description="执行状态")
    retry_count: int = Field(default=0, ge=0, description="已重试次数")
    started_at: datetime | None = Field(default=None, description="启动时间")
    finished_at: datetime | None = Field(default=None, description="结束时间")
    duration_seconds: float | None = Field(default=None, ge=0, description="运行时长（秒）")
    cached_from_run_id: UUID | None = Field(default=None, description="缓存命中来源 Run")


class NodeExecutionResponse(NodeExecutionListItem):
    """节点执行详情响应.

    Attributes
    ----------
    input_hash:
        输入数据哈希（sha256）。
    output_hash:
        输出数据哈希。
    params:
        参数快照。
    artifact_paths:
        产物路径列表。
    error:
        失败错误结构。
    logs_count:
        日志条目数。
    """

    input_hash: str | None = Field(default=None, description="输入哈希（sha256）")
    output_hash: str | None = Field(default=None, description="输出哈希（sha256）")
    params: dict[str, Any] = Field(default_factory=dict, description="参数快照")
    artifact_paths: list[str] = Field(default_factory=list, description="产物路径")
    error: dict[str, Any] | None = Field(default=None, description="失败错误")
    logs_count: int = Field(default=0, ge=0, description="日志条目数")


class NodeExecutionLogItem(BaseModel):
    """单条节点日志.

    Attributes
    ----------
    stream:
        日志流（``stdout`` / ``stderr`` / ``system``）。
    line:
        日志一行内容。
    logged_at:
        日志时间。
    """

    stream: Literal["stdout", "stderr", "system"] = Field(..., description="日志流")
    line: str = Field(..., description="日志内容")
    logged_at: datetime = Field(..., description="日志时间")


class NodeExecutionLogsResponse(BaseModel):
    """节点日志分页响应.

    Attributes
    ----------
    logs:
        日志条目。
    next_cursor:
        下一页游标（NULL 表示已到末尾）。
    """

    logs: list[NodeExecutionLogItem] = Field(default_factory=list, description="日志条目")
    next_cursor: str | None = Field(default=None, description="下一页游标")


# ===== Artifact =====


class ArtifactResponse(IDSchema):
    """产物响应.

    Attributes
    ----------
    artifact_type:
        产物类型。
    storage_path:
        存储路径（MinIO / S3 对象 key）。
    size_bytes:
        文件大小（字节）。
    sha256:
        文件 sha256（用于去重）。
    metadata:
        类型相关元数据（如 binner 的特征名）。
    download_url:
        预签名下载 URL（可选，过期时间由 storage 层控制）。
    node_id:
        产出该产物的节点在 DAG 中的稳定 ID（用于前端跳转）。
    node_type:
        节点类型（如 ``woe_encoder``）。
    node_name:
        节点中文名（来自 NodeContract.name）。
    output_name:
        输出端口名（如 ``binned_df`` / ``woe_features``）。
    created_at:
        产物创建时间（ISO-8601）。
    """

    artifact_type: ArtifactType = Field(..., description="产物类型")
    storage_path: str = Field(..., description="存储路径")
    size_bytes: int = Field(..., ge=0, description="文件大小（字节）")
    sha256: str = Field(..., description="sha256 哈希")
    metadata: dict[str, Any] = Field(default_factory=dict, description="类型相关元数据")
    download_url: str | None = Field(default=None, description="预签名下载 URL")

    node_id: str | None = Field(default=None, description="节点 ID（DAG 内）")
    node_type: str | None = Field(default=None, description="节点类型")
    node_name: str | None = Field(default=None, description="节点中文名")
    output_name: str | None = Field(default=None, description="输出端口名")
    created_at: datetime | None = Field(default=None, description="产物创建时间")


class ArtifactListResponse(BaseModel):
    """产物列表响应.

    Attributes
    ----------
    artifacts:
        产物列表。
    """

    artifacts: list[ArtifactResponse] = Field(default_factory=list, description="产物列表")


# ===== Run 控制 =====


class RunCancelResponse(BaseModel):
    """取消 Run 响应.

    Attributes
    ----------
    run_id:
        Run UUID。
    status:
        取消后状态（通常是 ``cancelled``）。
    cancelled_at:
        取消时间。
    message:
        人类可读描述（中文）。
    """

    run_id: UUID = Field(..., description="Run UUID")
    status: RunStatus = Field(..., description="取消后状态")
    cancelled_at: datetime = Field(..., description="取消时间")
    message: str = Field(..., description="描述")


class NodeRetryResponse(BaseModel):
    """节点重试响应.

    Attributes
    ----------
    node_exec_id:
        NodeExecution UUID。
    run_id:
        Run UUID。
    status:
        重置后的状态（``queued``）。
    message:
        中文描述（如「节点已重新入队」）。
    """

    node_exec_id: UUID = Field(..., description="NodeExecution UUID")
    run_id: UUID = Field(..., description="Run UUID")
    status: NodeExecutionStatus = Field(..., description="重置后的状态")
    message: str = Field(..., description="中文描述")


class RunMetricsResponse(BaseModel):
    """Run 指标响应.

    Attributes
    ----------
    run_id:
        Run UUID。
    metrics:
        运行级指标（KS / AUC / IV / PSI 等）。
    node_metrics:
        节点级指标（key 为节点 ID）。
    """

    run_id: UUID = Field(..., description="Run UUID")
    metrics: dict[str, Any] = Field(default_factory=dict, description="运行级指标")
    node_metrics: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="节点级指标（key 为节点 ID）",
    )


__all__ = [
    "ArtifactListResponse",
    "ArtifactResponse",
    "ArtifactType",
    "NodeExecutionListItem",
    "NodeExecutionLogItem",
    "NodeExecutionLogsResponse",
    "NodeExecutionResponse",
    "NodeExecutionStatus",
    "NodeRetryResponse",
    "RunCancelResponse",
    "RunListItem",
    "RunMetricsResponse",
    "RunResponse",
    "RunStatus",
    "RunSubmitRequest",
]
