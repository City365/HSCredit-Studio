"""审计事件 Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from hscredit_studio.schemas.common import PaginatedResponse


class AuditEventItem(BaseModel):
    """单条审计事件."""

    model_config = ConfigDict(from_attributes=True)

    event_id: UUID = Field(..., description="事件 UUID")
    tenant_id: UUID = Field(..., description="所属租户")
    user_id: UUID | None = Field(default=None, description="发起用户")
    action: str = Field(..., description="动作 (login/workflow_create/...)")
    resource_type: str | None = Field(default=None, description="资源类型")
    resource_id: UUID | None = Field(default=None, description="资源 ID")
    details: dict[str, Any] | None = Field(default=None, description="附加上下文")
    ip_address: str | None = Field(default=None, description="来源 IP")
    user_agent: str | None = Field(default=None, description="浏览器 UA")
    occurred_at: datetime = Field(..., description="发生时间")


class AuditEventListResponse(PaginatedResponse[AuditEventItem]):
    """审计事件分页响应."""


class AuditStats(BaseModel):
    """审计统计 (运营 Dashboard 用)."""

    total_events: int = Field(..., description="总事件数")
    unique_users: int = Field(..., description="活跃用户数")
    unique_actions: int = Field(..., description="不同动作数")
    last_24h_events: int = Field(..., description="最近 24h 事件数")
    last_7d_events: int = Field(..., description="最近 7 天事件数")
    by_action: list[dict[str, Any]] = Field(
        default_factory=list,
        description="按动作聚合统计 [{action, count}]",
    )
    by_user: list[dict[str, Any]] = Field(
        default_factory=list,
        description="按用户聚合 Top 10 [{user_id, email, count}]",
    )


__all__ = ["AuditEventItem", "AuditEventListResponse", "AuditStats"]