"""模型导出 Schemas — Phase 7 B34.

依据 docs/ROADMAP.md Phase 7 B34:

> 训练好的模型可导出为 PMML (金融行业标准)
> ONNX 格式 (云端部署)
> 包含校验: 导出后用 Java/ONNX Runtime 可加载并产生相同预测
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from hscredit_studio.services.model_export import ModelFormat, ModelType


class ModelExportRequest(BaseModel):
    """模型导出请求 (B34).

    模型以 base64 (pickle 序列化) 或 scorecard dict 形式传入.
    """

    model_b64: str = Field(..., description="Base64 编码的模型 (sklearn pickle / dict)")
    model_type: ModelType = ModelType.SKLEARN
    feature_names: list[str] = Field(..., min_length=1, description="入模特征名")
    format: ModelFormat = ModelFormat.PMML
    description: str | None = None


class ModelExportResponse(BaseModel):
    """模型导出响应 (B34 验收)."""

    format: ModelFormat
    model_type: ModelType
    filename: str
    mime_type: str
    file_size: int
    content_b64: str = Field(..., description="Base64 编码的导出文件")
    warnings: list[str]
    exported_at: datetime


class ModelValidationRequest(BaseModel):
    """模型校验请求 (B34 验收 — 跨平台一致性)."""

    original_model_b64: str
    exported_format: ModelFormat
    exported_content_b64: str
    sample_inputs: list[list[float]] = Field(..., min_length=1)
    tolerance: float = Field(1e-6, ge=0, le=1.0)


class ModelValidationResponse(BaseModel):
    """模型校验响应 (B34 验收)."""

    passed: bool
    max_abs_error: float
    mean_abs_error: float
    sample_count: int
    message: str
    tested_at: datetime
    original_predictions: list[float]
    exported_predictions: list[float]


# ===== 内置演示模型 =====


class DemoModelRequest(BaseModel):
    """生成演示评分卡模型请求 (用于 E2E 测试)."""

    feature_names: list[str] = Field(
        default_factory=lambda: ["age", "income", "credit_score"],
        min_length=1,
    )


class DemoModelResponse(BaseModel):
    """演示评分卡响应."""

    model_b64: str
    feature_names: list[str]
    coefficients: list[float]
    intercept: float
    description: str


__all__ = [
    "DemoModelRequest",
    "DemoModelResponse",
    "ModelExportRequest",
    "ModelExportResponse",
    "ModelValidationRequest",
    "ModelValidationResponse",
]
