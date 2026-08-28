"""模板共享 Schemas — Phase 6 B31."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PublishWorkflowRequest(BaseModel):
    """从工作流发布为模板请求 (B31 验收)."""

    workflow_id: UUID = Field(..., description="来源工作流 UUID")
    template_name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=4096)
    tags: list[str] = Field(default_factory=list)
    visibility: str = Field("tenant", description="private/tenant/public")


class PublishedTemplateResponse(BaseModel):
    """发布结果响应 (B31)."""

    template_id: UUID
    name: str
    visibility: str
    review_status: str
    source_workflow_id: UUID | None
    version_number: int
    node_count: int
    edge_count: int
    created_at: datetime


class CrossTenantShareRequest(BaseModel):
    """跨租户共享申请 (B31)."""

    target_tenants: list[UUID] = Field(..., min_length=1)
    reason: str | None = Field(None, max_length=512)


class ReviewDecisionRequest(BaseModel):
    """审核决定请求 (B31)."""

    approve: bool
    rejection_reason: str | None = Field(None, max_length=1024)
    comment: str | None = Field(None, max_length=1024)
    granted_tenants: list[UUID] = Field(default_factory=list)


class TemplateReviewLogItem(BaseModel):
    """审核日志项 (B31)."""

    model_config = ConfigDict(from_attributes=True)

    log_id: UUID
    template_id: UUID
    reviewer_id: UUID
    old_status: str | None
    new_status: str
    comment: str | None
    extra: dict[str, Any]
    created_at: datetime


class TemplateReviewLogList(BaseModel):
    """审核日志列表."""

    items: list[TemplateReviewLogItem]
    total: int


__all__ = [
    "CrossTenantShareRequest",
    "PublishWorkflowRequest",
    "PublishedTemplateResponse",
    "ReviewDecisionRequest",
    "TemplateReviewLogItem",
    "TemplateReviewLogList",
]
