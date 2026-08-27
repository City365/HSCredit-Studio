"""工作流相关 schema.

工作流 CRUD、版本管理、react-flow 节点/边序列化、导入导出等。

工作流定义 (``WorkflowDefinition``) 直接对应前端 react-flow 的序列化格式，
便于后端原样存储 + 解析后用于执行器构造 DAG。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from hscredit_studio.schemas.common import IDSchema, TimestampedSchema

# ===== react-flow 节点/边序列化 =====


class NodePosition(BaseModel):
    """react-flow 节点画布坐标.

    Attributes
    ----------
    x:
        X 坐标（像素）。
    y:
        Y 坐标（像素）。
    """

    x: float = Field(..., description="X 坐标")
    y: float = Field(..., description="Y 坐标")


class NodeDef(BaseModel):
    """react-flow 节点序列化结构.

    与前端 ``react-flow`` 库 :class:`Node` 类型对齐，确保前后端可直接
    互相序列化 / 反序列化。

    Attributes
    ----------
    id:
        节点 ID（在同一 workflow 内唯一；与 DAG 中的节点 ID 一致）。
    type:
        节点类型（注册表 key，如 ``optimal_binning_chi``）。
    position:
        画布坐标。
    data:
        用户填写的参数（按 :class:`NodeContract.params` 校验）。
    label:
        显示名（可选，默认使用注册表的 ``name``）。
    selected:
        前端临时选中状态（不应持久化）。
    """

    id: str = Field(..., min_length=1, max_length=128, description="节点 ID")
    type: str = Field(..., min_length=1, max_length=128, description="节点类型（注册表 key）")
    position: NodePosition = Field(..., description="画布坐标")
    data: dict[str, Any] = Field(default_factory=dict, description="用户填写的参数")
    label: str | None = Field(default=None, max_length=128, description="显示名")
    selected: bool | None = Field(default=None, description="前端选中状态（不持久化）")


class EdgeDef(BaseModel):
    """react-flow 边序列化结构.

    Attributes
    ----------
    id:
        边 ID（前端可自动生成，可选）。
    source:
        源节点 ID。
    target:
        目标节点 ID。
    source_handle:
        源端口 ID（多端口时区分）。
    target_handle:
        目标端口 ID（多端口时区分）。
    """

    id: str | None = Field(default=None, description="边 ID（可选）")
    source: str = Field(..., min_length=1, description="源节点 ID")
    target: str = Field(..., min_length=1, description="目标节点 ID")
    source_handle: str | None = Field(default=None, description="源端口 ID")
    target_handle: str | None = Field(default=None, description="目标端口 ID")


class WorkflowDefinition(BaseModel):
    """完整工作流定义（react-flow 序列化格式）.

    Attributes
    ----------
    nodes:
        节点列表。
    edges:
        边列表（连接关系）。
    viewport:
        react-flow 视口位置 ``{x, y, zoom}``，可空。
    metadata:
        自由 metadata（如注释、模板来源）。
    """

    nodes: list[NodeDef] = Field(default_factory=list, description="节点列表")
    edges: list[EdgeDef] = Field(default_factory=list, description="边列表")
    viewport: dict[str, float] | None = Field(default=None, description="视口位置 {x, y, zoom}")
    metadata: dict[str, Any] | None = Field(default=None, description="自由 metadata")


# ===== CRUD =====


class WorkflowCreate(BaseModel):
    """创建工作流请求体.

    Attributes
    ----------
    name:
        工作流名（1-200 字符）。
    description:
        描述（可选，<= 2000 字符）。
    tags:
        标签数组（最多 20 个）。
    definition:
        完整工作流定义。
    """

    name: str = Field(..., min_length=1, max_length=200, description="工作流名")
    description: str | None = Field(default=None, max_length=2000, description="描述")
    tags: list[str] = Field(default_factory=list, max_length=20, description="标签数组")
    definition: WorkflowDefinition = Field(..., description="工作流定义")


class WorkflowUpdate(BaseModel):
    """更新工作流请求体（PATCH 语义，所有字段可选）.

    Attributes
    ----------
    name:
        新名称。
    description:
        新描述。
    tags:
        新标签。
    definition:
        新工作流定义（会同时创建新版本，详见 service 层）。
    change_summary:
        变更说明（用于版本历史）。
    """

    name: str | None = Field(default=None, min_length=1, max_length=200, description="新名称")
    description: str | None = Field(default=None, max_length=2000, description="新描述")
    tags: list[str] | None = Field(default=None, max_length=20, description="新标签")
    definition: WorkflowDefinition | None = Field(default=None, description="新工作流定义")
    change_summary: str | None = Field(default=None, max_length=500, description="变更说明")


class WorkflowListItem(IDSchema, TimestampedSchema):
    """工作流列表项（精简字段）.

    Attributes
    ----------
    name:
        工作流名。
    description:
        描述。
    tags:
        标签数组。
    current_version_number:
        当前 HEAD 版本号（NULL 表示从未保存版本）。
    created_by:
        创建者 UUID。
    last_run_at:
        上次执行时间。
    last_run_status:
        上次执行状态。
    """

    name: str = Field(..., description="工作流名")
    description: str | None = Field(default=None, description="描述")
    tags: list[str] = Field(default_factory=list, description="标签数组")
    current_version_number: int | None = Field(default=None, description="当前版本号")
    created_by: UUID | None = Field(default=None, description="创建者 UUID")
    last_run_at: datetime | None = Field(default=None, description="上次执行时间")
    last_run_status: str | None = Field(default=None, description="上次执行状态")


class WorkflowResponse(WorkflowListItem):
    """工作流详情响应.

    Attributes
    ----------
    definition:
        当前 HEAD 版本的工作流定义（按需懒加载）。
    versions_count:
        历史版本总数。
    runs_count:
        历史执行总数。
    """

    definition: WorkflowDefinition | None = Field(default=None, description="当前工作流定义")
    versions_count: int = Field(default=0, ge=0, description="历史版本总数")
    runs_count: int = Field(default=0, ge=0, description="历史执行总数")


# ===== 版本管理 =====


class WorkflowVersionCreate(BaseModel):
    """创建工作流版本请求体.

    Attributes
    ----------
    change_summary:
        版本变更说明。
    definition:
        新版本的工作流定义。
    """

    change_summary: str | None = Field(default=None, max_length=500, description="变更说明")
    definition: WorkflowDefinition = Field(..., description="工作流定义")


class WorkflowVersionResponse(IDSchema, TimestampedSchema):
    """工作流版本详情响应.

    Attributes
    ----------
    workflow_id:
        所属工作流 UUID。
    version_number:
        版本号（自增）。
    definition:
        版本完整定义。
    change_summary:
        变更说明。
    created_by:
        创建者 UUID。
    """

    workflow_id: UUID = Field(..., description="所属工作流 UUID")
    version_number: int = Field(..., ge=1, description="版本号")
    definition: WorkflowDefinition = Field(..., description="工作流定义")
    change_summary: str | None = Field(default=None, description="变更说明")
    created_by: UUID | None = Field(default=None, description="创建者 UUID")


# ===== 导入导出 =====


class WorkflowExportRequest(BaseModel):
    """导出工作流请求体.

    Attributes
    ----------
    workflow_id:
        待导出的工作流 UUID。
    include_runs:
        是否同时导出最近若干次执行（用于复现）。
    """

    workflow_id: UUID = Field(..., description="工作流 UUID")
    include_runs: bool = Field(default=False, description="是否包含执行记录")


class WorkflowExportResponse(BaseModel):
    """导出工作流响应体.

    Attributes
    ----------
    workflow:
        工作流主体。
    latest_version:
        最新版本。
    runs:
        最近若干次执行（可选）。
    exported_at:
        导出时间。
    """

    workflow: WorkflowResponse = Field(..., description="工作流")
    latest_version: WorkflowVersionResponse = Field(..., description="最新版本")
    runs: list[dict[str, Any]] | None = Field(default=None, description="执行记录（可选）")
    exported_at: datetime = Field(..., description="导出时间")


class WorkflowImportRequest(BaseModel):
    """导入工作流请求体.

    Attributes
    ----------
    name:
        新名称（不指定则用导出包中的 name）。
    payload:
        来自 :class:`WorkflowExportResponse` 的字典结构。
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="新名称（可选）",
    )
    payload: dict[str, Any] = Field(..., description="来自 WorkflowExportResponse 的 payload")


__all__ = [
    "EdgeDef",
    "NodeDef",
    "NodePosition",
    "WorkflowCreate",
    "WorkflowDefinition",
    "WorkflowExportRequest",
    "WorkflowExportResponse",
    "WorkflowImportRequest",
    "WorkflowListItem",
    "WorkflowResponse",
    "WorkflowUpdate",
    "WorkflowVersionCreate",
    "WorkflowVersionResponse",
]
