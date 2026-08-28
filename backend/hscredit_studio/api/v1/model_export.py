"""模型导出 API — Phase 7 B34.

依据 docs/ROADMAP.md Phase 7 B34:

| 端点 | 方法 | 用途 |
|---|---|---|
| /model-export/export | POST | 模型导出 (PMML / ONNX) |
| /model-export/validate | POST | 导出校验 (跨平台一致性) |
| /model-export/demo-model | POST | 生成演示评分卡 (E2E 用) |
| /model-export/formats | GET | 列出支持的格式 |
"""
from __future__ import annotations

import pickle

from fastapi import APIRouter, HTTPException, status

from hscredit_studio.api.deps import CurrentUserDep
from hscredit_studio.schemas.model_export import (
    DemoModelRequest,
    DemoModelResponse,
    ModelExportRequest,
    ModelExportResponse,
    ModelValidationRequest,
    ModelValidationResponse,
)
from hscredit_studio.services import model_export as svc
from hscredit_studio.services.model_export import (
    ModelFormat,
    ModelType,
    decode_model_bytes,
    encode_model_bytes,
)

router = APIRouter(tags=["模型导出"])


@router.get(
    "/formats",
    summary="列出支持的导出格式 (B34)",
)
async def list_formats(_: CurrentUserDep) -> dict:
    return {
        "formats": [
            {
                "format": ModelFormat.PMML.value,
                "description": "PMML 4.4 — 金融行业标准 (JPMML-Evaluator 兼容)",
                "mime_type": "application/pmml+xml",
                "supported_models": [ModelType.SKLEARN.value, ModelType.SCORECARD.value],
                "tools": ["sklearn2pmml (推荐)", "JPMML-Evaluator (Java 加载)"],
            },
            {
                "format": ModelFormat.ONNX.value,
                "description": "ONNX — 云端部署 (ONNX Runtime 兼容)",
                "mime_type": "application/onnx",
                "supported_models": [ModelType.SKLEARN.value, ModelType.SCORECARD.value],
                "tools": ["skl2onnx (推荐)", "ONNX Runtime (跨语言加载)"],
            },
        ],
        "tolerance_default": 1e-6,
    }


@router.post(
    "/export",
    response_model=ModelExportResponse,
    summary="模型导出 (B34 验收)",
)
async def export_model(
    _: CurrentUserDep,
    body: ModelExportRequest,
) -> ModelExportResponse:
    """导出模型到 PMML 或 ONNX.

    支持:
    - sklearn 兼容 (LogisticRegression / DecisionTree / ...)
    - hscredit 评分卡 (dict 形式: {coefficients, intercept, name})
    """
    try:
        model_bytes = decode_model_bytes(body.model_b64)
        model = pickle.loads(model_bytes)
    except Exception as e:
        # 可能为 scorecard dict
        try:
            import base64 as _b64
            import json as _json

            model = _json.loads(_b64.b64decode(body.model_b64).decode("utf-8"))
        except Exception as e2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "E_MODEL_DECODE",
                    "message": f"模型解析失败: pickle={e}, json={e2}",
                },
            ) from e2

    if body.format == ModelFormat.PMML:
        result = svc.export_to_pmml(
            model=model,
            feature_names=body.feature_names,
            model_type=body.model_type,
        )
    elif body.format == ModelFormat.ONNX:
        result = svc.export_to_onnx(
            model=model,
            feature_names=body.feature_names,
            model_type=body.model_type,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "E_UNSUPPORTED_FORMAT", "message": f"不支持的格式: {body.format}"},
        )

    return ModelExportResponse(
        format=result.format,
        model_type=result.model_type,
        filename=result.filename,
        mime_type=result.mime_type,
        file_size=len(result.bytes_content),
        content_b64=encode_model_bytes(result.bytes_content),
        warnings=result.warnings,
        exported_at=result.exported_at,
    )


@router.post(
    "/validate",
    response_model=ModelValidationResponse,
    summary="导出校验 (B34 验收 — 跨平台一致性)",
)
async def validate_export(
    _: CurrentUserDep,
    body: ModelValidationRequest,
) -> ModelValidationResponse:
    """校验导出模型的预测一致性.

    比较原模型与导出模型在 sample_inputs 上的预测值,
    max_abs_error 应 < tolerance (默认 1e-6).
    """
    try:
        original_bytes = decode_model_bytes(body.original_model_b64)
        original_model = pickle.loads(original_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "E_ORIGINAL_DECODE", "message": str(e)},
        ) from e

    exported_bytes = decode_model_bytes(body.exported_content_b64)

    result = svc.validate_export(
        original_model=original_model,
        exported_format=body.exported_format,
        exported_bytes=exported_bytes,
        sample_inputs=body.sample_inputs,
        tolerance=body.tolerance,
    )

    return ModelValidationResponse(
        passed=result.passed,
        max_abs_error=result.max_abs_error,
        mean_abs_error=result.mean_abs_error,
        sample_count=result.sample_count,
        message=result.message,
        tested_at=result.tested_at,
        original_predictions=result.original_predictions,
        exported_predictions=result.exported_predictions,
    )


@router.post(
    "/demo-model",
    response_model=DemoModelResponse,
    summary="生成演示评分卡 (B34 E2E 用)",
)
async def demo_model(
    _: CurrentUserDep,
    body: DemoModelRequest,
) -> DemoModelResponse:
    """生成一个简单的演示评分卡模型, 用于 E2E 验证导出/校验流程."""
    scorecard = {
        "name": "DemoCreditScorecard",
        "coefficients": [0.05, 0.0001, 0.02],
        "intercept": -3.5,
    }
    # 截断/扩展到 feature 数
    while len(scorecard["coefficients"]) < len(body.feature_names):
        scorecard["coefficients"].append(0.01)
    scorecard["coefficients"] = scorecard["coefficients"][: len(body.feature_names)]

    import base64 as _b64
    import json as _json

    b64 = _b64.b64encode(_json.dumps(scorecard).encode("utf-8")).decode("ascii")

    return DemoModelResponse(
        model_b64=b64,
        feature_names=body.feature_names,
        coefficients=scorecard["coefficients"],
        intercept=scorecard["intercept"],
        description="演示评分卡 (用于 PMML/ONNX 导出 + 校验 E2E)",
    )


__all__ = ["router"]
