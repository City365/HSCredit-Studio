"""自定义节点 Pydantic schemas — Phase 6 B36.

包含 4 类:
- CustomNodeCreateRequest / CustomNodeUpdateRequest / CustomNodeResponse
- CustomNodeVersionResponse
- CustomNodeDraftRequest / CustomNodeDraftResponse
- CustomNodeLockResponse
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from hscredit_studio.schemas.node_contract import NodeContract


# ===== 节点 CRUD =====


VISIBILITY_VALUES = Literal["private", "tenant", "public"]


class CustomNodeCreateRequest(BaseModel):
    """创建自定义节点请求.

    创建时必须含 v1 版本 code + contract. 后续版本通过 /code 端点提交.
    """

    node_type: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="节点类型 (小写字母数字下划线, 必须以字母开头)",
    )
    name: str = Field(..., min_length=1, max_length=128, description="中文显示名")
    category: str = Field(default="特征工程", min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=32, description="图标 (emoji)")
    visibility: VISIBILITY_VALUES = Field(default="private", description="可见性")
    code: str = Field(..., min_length=1, max_length=500_000, description="v1 版本 Python 源码")
    contract: NodeContract = Field(..., description="节点契约")
    requirements: str | None = Field(default=None, max_length=10_000, description="依赖白名单 (requirements.txt 内容)")

    @field_validator("node_type")
    @classmethod
    def _validate_node_type(cls, v: str) -> str:
        """确保 node_type 格式合法."""
        if not v[0].isalpha():
            raise ValueError("node_type 必须以字母开头")
        return v


class CustomNodeUpdateRequest(BaseModel):
    """更新节点元数据 (不含 code / contract)."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=32)
    visibility: VISIBILITY_VALUES | None = None
    enabled: bool | None = None


class CustomNodeUpdateCodeRequest(BaseModel):
    """提交新版本代码请求."""

    code: str = Field(..., min_length=1, max_length=500_000)
    contract: NodeContract = Field(..., description="新版本的 contract (与代码保持一致)")
    change_summary: str | None = Field(default=None, max_length=500, description="本次变更说明")


class CustomNodeResponse(BaseModel):
    """节点详情响应."""

    custom_node_id: uuid.UUID
    tenant_id: uuid.UUID
    node_type: str
    name: str
    category: str
    description: str | None
    icon: str | None
    visibility: str
    enabled: bool
    contract: dict[str, Any]
    current_version_number: int | None
    current_version_id: uuid.UUID | None
    test_run_count: int
    last_test_run_at: datetime | None
    locked_by: uuid.UUID | None
    locked_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CustomNodeListItem(BaseModel):
    """列表项 (轻量)."""

    custom_node_id: uuid.UUID
    node_type: str
    name: str
    category: str
    visibility: str
    enabled: bool
    icon: str | None
    current_version_number: int | None
    test_run_count: int
    last_test_run_at: datetime | None
    updated_at: datetime

    class Config:
        from_attributes = True


class CustomNodeListResponse(BaseModel):
    """列表响应 (含分页)."""

    items: list[CustomNodeListItem]
    total: int
    page: int = 1
    page_size: int = 20


# ===== 版本管理 =====


class CustomNodeVersionResponse(BaseModel):
    """版本详情响应."""

    version_id: uuid.UUID
    custom_node_id: uuid.UUID
    version_number: int
    code: str
    contract: dict[str, Any]
    requirements: str | None
    change_summary: str | None
    created_by: uuid.UUID | None
    created_at: datetime

    class Config:
        from_attributes = True


class CustomNodeVersionListResponse(BaseModel):
    items: list[CustomNodeVersionResponse]
    total: int


# ===== 草稿 =====


class CustomNodeDraftRequest(BaseModel):
    """保存草稿请求 (静默调用)."""

    code: str = Field(..., min_length=1, max_length=500_000)
    contract_preview: dict[str, Any] | None = Field(default=None, description="AST 反推的 contract 预览 (缓存)")
    validation_status: Literal["draft", "validating", "valid", "invalid"] = "draft"
    validation_issues: dict[str, Any] | None = None


class CustomNodeDraftResponse(BaseModel):
    draft_id: uuid.UUID
    custom_node_id: uuid.UUID
    draft_code: str
    draft_contract: dict[str, Any]
    contract_preview: dict[str, Any] | None
    validation_status: str
    validation_issues: dict[str, Any] | None
    last_validation_at: datetime | None
    updated_at: datetime

    class Config:
        from_attributes = True


# ===== 编辑锁 =====


class CustomNodeLockResponse(BaseModel):
    lock_id: uuid.UUID
    node_type: str
    tenant_id: uuid.UUID
    locked_by: uuid.UUID
    locked_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


# ===== 校验 / 反推 / 试运行 =====


class ValidateRequest(BaseModel):
    """AST 静态校验请求."""

    code: str = Field(..., min_length=1, max_length=500_000)


class ValidationIssueResponse(BaseModel):
    """单个校验问题."""

    line: int
    column: int = 0
    severity: str  # 'error' / 'warning'
    rule: str
    message: str


class ValidateResponse(BaseModel):
    valid: bool
    issues: list[ValidationIssueResponse]
    ast_preview: dict[str, Any] | None = None


class DetectContractRequest(BaseModel):
    """Contract 反推请求 (AST + 试运行)."""

    code: str = Field(..., min_length=1, max_length=500_000)
    sample_data: dict[str, Any] | None = Field(
        default=None,
        description="可选: 试运行用的 sample inputs (DataFrame 列定义等)",
    )


class DetectContractResponse(BaseModel):
    """Contract 反推响应."""

    draft_contract: dict[str, Any]
    ast_inferred: dict[str, Any]
    runtime_inferred: dict[str, Any] | None
    warnings: list[str]


class TestRunRequest(BaseModel):
    """试运行请求."""

    version_id: uuid.UUID | None = Field(
        default=None, description="指定版本 (默认 current_version)",
    )
    sample_inputs: dict[str, Any] = Field(default_factory=dict, description="输入端口 sample")
    sample_params: dict[str, Any] = Field(default_factory=dict, description="参数 sample")
    sample_data: dict[str, Any] | None = Field(
        default=None,
        description="可选: 喂给 DataFrame 端口的 sample data (CSV/JSON)",
    )


class TestRunResponse(BaseModel):
    """试运行响应."""

    test_run_id: uuid.UUID
    status: str  # 'success' / 'failed' / 'timeout' / 'oom'
    duration_ms: int
    outputs: dict[str, Any] | None = None
    logs: list[str] = Field(default_factory=list)
    resource_usage: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


__all__ = [
    "CustomNodeCreateRequest",
    "CustomNodeDraftRequest",
    "CustomNodeDraftResponse",
    "CustomNodeListItem",
    "CustomNodeListResponse",
    "CustomNodeLockResponse",
    "CustomNodeResponse",
    "CustomNodeUpdateCodeRequest",
    "CustomNodeUpdateRequest",
    "CustomNodeVersionListResponse",
    "CustomNodeVersionResponse",
    "DetectContractRequest",
    "DetectContractResponse",
    "TestRunRequest",
    "TestRunResponse",
    "ValidateRequest",
    "ValidateResponse",
    "ValidationIssueResponse",
    "VISIBILITY_VALUES",
]
