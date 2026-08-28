"""行业模板市场 Schemas — Phase 6 B30.

依据 docs/ROADMAP.md Phase 6 B30:

- 6 个行业模板 (银行信用卡 / 消金 / 助贷 / 现金贷 / 电商分期 / 汽车金融)
- 模板预览 (只读)
- 一键实例化 (POST /workflows via template_id)
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IndustryTemplateSummary(BaseModel):
    """行业模板摘要 (B30 模板市场列表)."""

    model_config = ConfigDict(from_attributes=True)

    template_id: UUID
    name: str
    industry: str
    category: str
    description: str | None
    icon: str | None
    tags: list[str]
    target_column: str
    model_type: str
    score_formula: str
    node_count: int
    edge_count: int
    recommended_features: list[str]
    use_count: int
    rating_avg: float | None
    rating_count: int


class IndustryTemplateListResponse(BaseModel):
    """模板市场列表 (B30 验收)."""

    items: list[IndustryTemplateSummary]
    total: int


class IndustryTemplateDetail(BaseModel):
    """行业模板详情 (B30 预览, 含完整 nodes/edges + 元数据)."""

    model_config = ConfigDict(from_attributes=True)

    template_id: UUID
    name: str
    industry: str
    category: str
    description: str | None
    icon: str | None
    tags: list[str]
    target_column: str
    recommended_features: list[str]
    model_type: str
    score_formula: str
    report_template: str
    default_dataset: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    version_number: int
    use_count: int


class IndustryTemplateInstantiateRequest(BaseModel):
    """模板实例化请求 (B30 一键实例化)."""

    workflow_name: str | None = Field(None, description="新工作流名 (默认 模板名_时间戳)")
    params_overrides: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="按 node_id 覆盖节点 data 字段",
    )


class IndustryTemplateInstantiateResponse(BaseModel):
    """模板实例化响应 (B30 一键实例化)."""

    template_id: UUID
    template_name: str
    workflow_id: UUID
    workflow_name: str
    node_count: int
    edge_count: int
    created_at: str


class IndustryTemplateRatingCreate(BaseModel):
    """模板评分提交 (B30)."""

    rating: int = Field(..., ge=1, le=5, description="1-5 星")
    comment: str | None = Field(None, max_length=1024)


class IndustryTemplateRatingResponse(BaseModel):
    """模板评分响应 (B30)."""

    template_id: UUID
    rating_id: UUID
    rating: int
    rating_avg: float | None
    rating_count: int


__all__ = [
    "IndustryTemplateDetail",
    "IndustryTemplateInstantiateRequest",
    "IndustryTemplateInstantiateResponse",
    "IndustryTemplateListResponse",
    "IndustryTemplateRatingCreate",
    "IndustryTemplateRatingResponse",
    "IndustryTemplateSummary",
]
