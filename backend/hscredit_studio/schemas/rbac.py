"""RBAC Pydantic Schemas — Phase 6 B28."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RoleInfo(BaseModel):
    """角色信息 — Phase 6 B28."""

    model_config = ConfigDict(from_attributes=True)

    role: str = Field(..., description="角色值 (super_admin / tenant_admin / analyst / viewer)")
    label: str = Field(..., description="中文显示名")
    rank: int = Field(..., description="权限等级 (越大权限越高)")
    is_tenant_scoped: bool = Field(..., description="是否租户内角色")
    description: str = Field("", description="角色职责说明")


class PermissionCheckRequest(BaseModel):
    """权限校验请求 — Phase 6 B28."""

    resource: str = Field(..., description="资源: workflow/run/model/template/billing")
    action: str = Field(..., description="动作: read/write/admin")


class PermissionCheckResponse(BaseModel):
    """权限校验响应 — Phase 6 B28."""

    allowed: bool
    role: str
    resource: str
    action: str
    reason: str = ""


class PermissionMatrixResponse(BaseModel):
    """权限矩阵查询响应 — Phase 6 B28."""

    roles: list[RoleInfo]
    resources: list[str]
    matrix: dict[str, dict[str, str | None]] = Field(
        ..., description="{role: {resource: action | None}}",
    )


class MenuResponse(BaseModel):
    """前端菜单可见性响应 — Phase 6 B28."""

    role: str
    items: list[str]


class RolePolicyCreate(BaseModel):
    """角色策略创建请求 — Phase 6 B28."""

    role: str = Field(..., description="角色")
    resource: str = Field(..., description="资源")
    allowed_action: str = Field(..., description="read/write/admin")
    tenant_id: UUID | None = Field(None, description="NULL=全局, 否则=租户级覆盖")
    enabled: bool = True
    comment: str | None = None


class RolePolicyResponse(BaseModel):
    """角色策略响应 — Phase 6 B28."""

    model_config = ConfigDict(from_attributes=True)

    policy_id: UUID
    role: str
    resource: str
    allowed_action: str
    tenant_id: UUID | None
    enabled: bool
    comment: str | None
    created_at: datetime


class RoleAuditItem(BaseModel):
    """角色变更审计项 — Phase 6 B28."""

    model_config = ConfigDict(from_attributes=True)

    audit_id: UUID
    tenant_id: UUID
    user_id: UUID
    old_role: str | None
    new_role: str
    changed_by: UUID
    reason: str | None
    extra: dict[str, Any]
    created_at: datetime


class RoleAuditListResponse(BaseModel):
    """角色审计列表 — Phase 6 B28."""

    items: list[RoleAuditItem]
    total: int


__all__ = [
    "MenuResponse",
    "PermissionCheckRequest",
    "PermissionCheckResponse",
    "PermissionMatrixResponse",
    "RoleAuditItem",
    "RoleAuditListResponse",
    "RoleInfo",
    "RolePolicyCreate",
    "RolePolicyResponse",
]
