"""PIPL Schema — Phase 5 B26.

依据 docs/ROADMAP.md Phase 5 B26:

> 用户权利实现: 查询、更正、删除、可携
> 数据流图 + 跨境传输审批
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ===== 同意 =====


class ConsentGrantRequest(BaseModel):
    """授予同意请求."""

    model_config = ConfigDict(from_attributes=True)

    purpose: str = Field(..., pattern="^(service_provision|billing|marketing|analytics|third_party_sharing)$")
    policy_version: str = Field(default="v1.0", max_length=32)
    source: str | None = Field(default=None, max_length=64)


class ConsentRevokeRequest(BaseModel):
    """撤回同意请求."""

    model_config = ConfigDict(from_attributes=True)

    purpose: str = Field(..., pattern="^(service_provision|billing|marketing|analytics|third_party_sharing)$")
    reason: str | None = None


class ConsentStateResponse(BaseModel):
    """同意状态响应."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    purpose: str
    granted: bool
    granted_at: str | None
    revoked_at: str | None
    policy_version: str
    consent_id: str | None


# ===== 数据主体请求 (DSR) =====


class DsrSubmitRequest(BaseModel):
    """数据主体请求提交."""

    model_config = ConfigDict(from_attributes=True)

    request_type: str = Field(
        ..., pattern="^(access|correction|deletion|portability|withdraw_consent)$"
    )
    reason: str | None = None
    payload: dict[str, Any] | None = None


class DsrSubmitResponse(BaseModel):
    """DSR 提交响应."""

    model_config = ConfigDict(from_attributes=True)

    request_id: str
    submitted_at: str
    due_at: str
    status: str


class DsrListItem(BaseModel):
    """DSR 列表项."""

    model_config = ConfigDict(from_attributes=True)

    request_id: str
    request_type: str
    status: str
    reason: str | None
    submitted_at: datetime
    due_at: datetime
    completed_at: datetime | None


class DsrProcessRequest(BaseModel):
    """DSR 处理请求 (DPA/Admin)."""

    model_config = ConfigDict(from_attributes=True)

    new_status: str = Field(..., pattern="^(verifying|in_progress|completed|rejected)$")
    response: dict[str, Any] | None = None
    rejection_reason: str | None = None


# ===== 数据可携 (portability) =====


class UserDataPackageResponse(BaseModel):
    """用户数据可携包响应."""

    model_config = ConfigDict(from_attributes=True)

    export_id: str
    exported_at: str
    user_info: dict[str, Any]
    consents: list[dict[str, Any]]
    data_subject_requests: list[dict[str, Any]]
    audit_events_count: int
    audit_events_sample: list[dict[str, Any]]
    package_hash: str


# ===== 匿名化 =====


class AnonymizationResponse(BaseModel):
    """匿名化响应."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    anonymized_tables: list[str]
    anonymized_at: str
    fields_cleared: dict[str, int]


# ===== 跨境传输 =====


class CrossBorderRequestSchema(BaseModel):
    """跨境传输申请."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str | None = None
    destination_country: str = Field(..., min_length=2, max_length=8)
    destination_entity: str = Field(..., max_length=256)
    data_categories: list[str] = Field(default_factory=list)
    legal_basis: str = Field(
        ..., pattern="^(cac_assessment|standard_contract|certification|explicit_consent)$"
    )
    legal_basis_ref: str | None = None


class CrossBorderApproveRequest(BaseModel):
    """跨境传输审批."""

    model_config = ConfigDict(from_attributes=True)

    approved: bool
    notes: str | None = None


class CrossBorderResponse(BaseModel):
    """跨境传输记录响应."""

    model_config = ConfigDict(from_attributes=True)

    transfer_id: str
    destination_country: str
    destination_entity: str
    legal_basis: str
    approved: bool | None
    approver_id: str | None
    approved_at: datetime | None


# ===== 隐私政策 =====


class PrivacyPolicyResponse(BaseModel):
    """隐私政策响应."""

    model_config = ConfigDict(from_attributes=True)

    version: str
    title: str
    content: str
    published_at: datetime
    is_current: bool


__all__ = [
    "AnonymizationResponse",
    "ConsentGrantRequest",
    "ConsentRevokeRequest",
    "ConsentStateResponse",
    "CrossBorderApproveRequest",
    "CrossBorderRequestSchema",
    "CrossBorderResponse",
    "DsrListItem",
    "DsrProcessRequest",
    "DsrSubmitRequest",
    "DsrSubmitResponse",
    "PrivacyPolicyResponse",
    "UserDataPackageResponse",
]
