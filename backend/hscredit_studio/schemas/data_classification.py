"""数据脱敏 Schema — Phase 5 B24.

依据 docs/ROADMAP.md Phase 5 B24:

> 高敏字段自动脱敏 (前端展示 mask, 后端日志 hash)
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hscredit_studio.services.data_classification import DataSensitivity


class FieldClassificationInfo(BaseModel):
    """字段分类详情."""

    model_config = ConfigDict(from_attributes=True)

    field_name: str
    sensitivity: DataSensitivity
    description: str = Field(default="")


class MaskResult(BaseModel):
    """单字段脱敏结果."""

    model_config = ConfigDict(from_attributes=True)

    field_name: str
    original_length: int = Field(description="原始值长度")
    masked_value: str = Field(description="脱敏后值")
    field_value_hash: str = Field(description="原始值 SHA256 截断 hash")


class RedactRequest(BaseModel):
    """批量脱敏请求 — Phase 5 B24 验收."""

    model_config = ConfigDict(from_attributes=True)

    payload: dict[str, Any] = Field(description="待脱敏的 dict (含敏感字段)")
    threshold: DataSensitivity = Field(
        default=DataSensitivity.SENSITIVE,
        description="阈值, ≥ 该敏感度的字段将被脱敏",
    )


class RedactResponse(BaseModel):
    """批量脱敏响应."""

    model_config = ConfigDict(from_attributes=True)

    redacted: dict[str, Any] = Field(description="脱敏后的 dict")
    fields_redacted: list[str] = Field(
        default_factory=list, description="本次被脱敏的字段名列表"
    )


__all__ = [
    "FieldClassificationInfo",
    "MaskResult",
    "RedactRequest",
    "RedactResponse",
]
