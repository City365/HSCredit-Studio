"""租户超管后台 Schemas — Phase 6 B29."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TenantOverviewItem(BaseModel):
    """单个租户概览 (B29 跨租户仪表板)."""

    model_config = ConfigDict(from_attributes=True)

    tenant_id: str
    slug: str
    name: str
    plan: str
    status: str
    member_count: int
    total_runs_30d: int
    total_cpu_seconds_30d: float
    last_active_at: datetime | None
    is_healthy: bool


class GlobalOverviewResponse(BaseModel):
    """全平台跨租户概览 (B29 仪表板顶层)."""

    total_tenants: int
    active_tenants: int
    suspended_tenants: int
    archived_tenants: int
    total_members: int
    total_runs_30d: int
    total_cpu_seconds_30d: float
    top_tenants_by_runs: list[TenantOverviewItem]
    plan_distribution: dict[str, int]
    generated_at: datetime


class TenantListItem(BaseModel):
    """租户列表项 (B29)."""

    model_config = ConfigDict(from_attributes=True)

    tenant_id: UUID
    slug: str
    name: str
    plan: str
    status: str
    created_at: datetime
    updated_at: datetime


class TenantListResponse(BaseModel):
    """租户分页列表 (B29)."""

    items: list[TenantListItem]
    total: int
    page: int
    page_size: int


class TenantMemberInfo(BaseModel):
    """租户成员信息 (B29 详情)."""

    user_id: UUID
    email: str
    display_name: str | None
    role: str
    status: str
    joined_at: datetime


class TenantUsageInfo(BaseModel):
    """租户用量 (30 天) (B29 详情)."""

    total_runs: int
    total_cpu_seconds: float
    total_duration_ms: int
    max_mem_peak_mb: float


class TenantTrendPoint(BaseModel):
    """30 天用量趋势点 (B29)."""

    date: str
    runs: int


class TenantAuditEventInfo(BaseModel):
    """审计事件信息 (B29 详情)."""

    event_id: UUID
    action: str
    user_id: UUID | None
    resource_type: str | None
    resource_id: UUID | None
    occurred_at: datetime


class TenantDetailResponse(BaseModel):
    """租户详情 (B29)."""

    tenant_id: UUID
    slug: str
    name: str
    plan: str
    status: str
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    members: list[TenantMemberInfo]
    usage_30d: TenantUsageInfo
    usage_trend_30d: list[TenantTrendPoint]
    recent_audit_events: list[TenantAuditEventInfo]


class TenantStatusUpdateRequest(BaseModel):
    """租户状态变更请求 (B29 启用/停用)."""

    status: str = Field(..., description="active/suspended/archived")


class TenantStatusUpdateResponse(BaseModel):
    """租户状态变更响应 (B29)."""

    tenant_id: UUID
    status: str
    updated_at: datetime


class TenantMigrateRequest(BaseModel):
    """租户迁移请求 (B29)."""

    target_cluster: str = Field(..., min_length=1, max_length=64)


class TenantMigrateResponse(BaseModel):
    """租户迁移响应 (B29)."""

    tenant_id: UUID
    target_cluster: str
    migrated_at: str


class RoleChangeRequest(BaseModel):
    """用户角色变更请求 (B29 + B28 联动)."""

    new_role: str = Field(..., description="owner/admin/analyst/viewer")
    reason: str | None = Field(None, max_length=512)


class RoleChangeResponse(BaseModel):
    """用户角色变更响应 (B29)."""

    tenant_id: UUID
    user_id: UUID
    old_role: str
    new_role: str
    changed_by: UUID
    changed_at: datetime


__all__ = [
    "GlobalOverviewResponse",
    "RoleChangeRequest",
    "RoleChangeResponse",
    "TenantAuditEventInfo",
    "TenantDetailResponse",
    "TenantListItem",
    "TenantListResponse",
    "TenantMemberInfo",
    "TenantMigrateRequest",
    "TenantMigrateResponse",
    "TenantOverviewItem",
    "TenantStatusUpdateRequest",
    "TenantStatusUpdateResponse",
    "TenantTrendPoint",
    "TenantUsageInfo",
]
