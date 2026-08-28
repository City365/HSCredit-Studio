"""数据分类与脱敏 API — Phase 5 B24.

依据 docs/ROADMAP.md Phase 5 B24 验收:

- ``GET  /api/v1/{tenant}/data-classification/fields`` — 列出预置字段分类
- ``POST /api/v1/{tenant}/data-classification/redact`` — 批量脱敏 payload
- ``POST /api/v1/{tenant}/data-classification/mask`` — 单字段脱敏 + hash
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from hscredit_studio.schemas.data_classification import (
    FieldClassificationInfo,
    MaskResult,
    RedactRequest,
    RedactResponse,
)
from hscredit_studio.services.data_classification import (
    DEFAULT_FIELD_CLASSIFICATION,
    DataSensitivity,
    classify_field,
    hash_value,
    mask_value,
    redact_payload,
)

router = APIRouter(tags=["数据脱敏"])


@router.get("/fields", summary="预置字段分类列表")
async def list_classified_fields() -> dict[str, Any]:
    """Phase 5 B24 — 列出所有预置字段分级."""
    items = [
        FieldClassificationInfo(
            field_name=k,
            sensitivity=v,
            description=_describe(v),
        )
        for k, v in DEFAULT_FIELD_CLASSIFICATION.items()
    ]
    return {"items": [i.model_dump() for i in items], "count": len(items)}


@router.post("/redact", response_model=RedactResponse, summary="批量脱敏 payload")
async def redact_endpoint(body: RedactRequest = Body(...)) -> RedactResponse:
    """Phase 5 B24 — 批量脱敏 dict/list 中的敏感字段.

    适用场景: 租户自助查询返回前端前, 后端用此 API 清洗一遍.
    """
    threshold = body.threshold
    redacted = redact_payload(body.payload, sensitivity_threshold=threshold)

    # 记录被脱敏的字段 (遍历原始 payload, 比对分类)
    redacted_fields: list[str] = []

    def _walk(obj: dict | list, original: dict | list) -> None:
        if isinstance(obj, dict) and isinstance(original, dict):
            for k in obj:
                sensitivity = classify_field(k)
                # threshold + 未嵌套 → 计入被脱敏
                if (
                    _sensitivity_rank(sensitivity) >= _sensitivity_rank(threshold)
                    and not isinstance(obj[k], (dict, list))
                ):
                    redacted_fields.append(k)
                if isinstance(obj[k], (dict, list)) and isinstance(original.get(k), (dict, list)):
                    _walk(obj[k], original[k])

    _walk(redacted, body.payload)

    return RedactResponse(redacted=redacted, fields_redacted=redacted_fields)


@router.post("/mask", response_model=MaskResult, summary="单字段脱敏 + hash")
async def mask_endpoint(
    field_name: str = Body(..., embed=True),
    value: Any = Body(..., embed=True),
) -> MaskResult:
    """Phase 5 B24 — 单字段脱敏 + 原始值 hash."""
    masked = mask_value(field_name, value)
    return MaskResult(
        field_name=field_name,
        original_length=len(str(value)) if value is not None else 0,
        masked_value=masked,
        field_value_hash=hash_value(value),
    )


_SENSITIVITY_RANK: dict[DataSensitivity, int] = {
    DataSensitivity.PUBLIC: 0,
    DataSensitivity.INTERNAL: 1,
    DataSensitivity.SENSITIVE: 2,
    DataSensitivity.HIGHLY_SENSITIVE: 3,
}


def _sensitivity_rank(s: DataSensitivity) -> int:
    return _SENSITIVITY_RANK[s]


def _describe(s: DataSensitivity) -> str:
    return {
        DataSensitivity.PUBLIC: "公开 — 无需脱敏",
        DataSensitivity.INTERNAL: "内部 — 仅内部访问, 不展示给最终用户",
        DataSensitivity.SENSITIVE: "敏感 — 业务敏感, 前端展示需 mask",
        DataSensitivity.HIGHLY_SENSITIVE: "高敏 — 法律合规级, 日志需 hash, 前端需 mask",
    }.get(s, "")


__all__ = ["router"]
