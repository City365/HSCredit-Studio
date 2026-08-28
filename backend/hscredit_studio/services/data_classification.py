"""数据分类与脱敏 — Phase 5 B24.

依据 docs/ROADMAP.md Phase 5 B24:

> 字段分级: 公开 / 内部 / 敏感 / 高敏 (身份证/手机号/银行卡)
> 高敏字段自动脱敏 (前端展示 mask, 后端日志 hash)
> 数据访问审计: B20 每次读敏感字段写 audit event

设计:

- :class:`DataSensitivity` — 枚举: PUBLIC / INTERNAL / SENSITIVE / HIGHLY_SENSITIVE
- :data:`DEFAULT_FIELD_CLASSIFICATION` — 预置字段名 → 分级映射
- :func:`classify_field` — 按字段名查分级
- :func:`mask_value` — 前端展示用脱敏 (eg: 138****1234)
- :func:`hash_value` — 日志用 hash (SHA256 截断)
- :func:`redact_payload` — 递归清洗 dict / list 中的敏感字段
"""
from __future__ import annotations

import hashlib
import re
from enum import Enum
from typing import Any


class DataSensitivity(str, Enum):  # noqa: UP042
    """数据敏感度分级 (Phase 5 B24).

    - PUBLIC: 可对外公开 (产品介绍/官网文案)
    - INTERNAL: 仅内部使用 (公司财报/运营指标)
    - SENSITIVE: 业务敏感 (手机号/邮箱/地址)
    - HIGHLY_SENSITIVE: 法律合规级别 (身份证/银行卡/人脸)
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    HIGHLY_SENSITIVE = "highly_sensitive"


# ===== 字段分类映射 =====

DEFAULT_FIELD_CLASSIFICATION: dict[str, DataSensitivity] = {
    # 高敏 — 合规级 (金融/PIPL 严管)
    "id_card": DataSensitivity.HIGHLY_SENSITIVE,
    "身份证": DataSensitivity.HIGHLY_SENSITIVE,
    "id_number": DataSensitivity.HIGHLY_SENSITIVE,
    "bank_card": DataSensitivity.HIGHLY_SENSITIVE,
    "银行卡号": DataSensitivity.HIGHLY_SENSITIVE,
    "credit_card": DataSensitivity.HIGHLY_SENSITIVE,
    "cvv": DataSensitivity.HIGHLY_SENSITIVE,
    "passport": DataSensitivity.HIGHLY_SENSITIVE,
    "social_security": DataSensitivity.HIGHLY_SENSITIVE,
    # 敏感 — 业务级
    "phone": DataSensitivity.SENSITIVE,
    "mobile": DataSensitivity.SENSITIVE,
    "手机号": DataSensitivity.SENSITIVE,
    "email": DataSensitivity.SENSITIVE,
    "address": DataSensitivity.SENSITIVE,
    "地址": DataSensitivity.SENSITIVE,
    "birthday": DataSensitivity.SENSITIVE,
    "生日": DataSensitivity.SENSITIVE,
    "salary": DataSensitivity.SENSITIVE,
    "工资": DataSensitivity.SENSITIVE,
    "income": DataSensitivity.SENSITIVE,
    # 内部
    "tenant_id": DataSensitivity.INTERNAL,
    "user_id": DataSensitivity.INTERNAL,
    "internal_note": DataSensitivity.INTERNAL,
    # 公开 — 无需脱敏 (白名单)
    "id": DataSensitivity.PUBLIC,
    "name": DataSensitivity.PUBLIC,
    "status": DataSensitivity.PUBLIC,
    "created_at": DataSensitivity.PUBLIC,
    "updated_at": DataSensitivity.PUBLIC,
}


# ===== 分类查找 =====


def classify_field(field_name: str) -> DataSensitivity:
    """根据字段名查敏感度分级 (Phase 5 B24).

    默认: 不在映射表的字段视为 INTERNAL (保守).
    """
    if field_name in DEFAULT_FIELD_CLASSIFICATION:
        return DEFAULT_FIELD_CLASSIFICATION[field_name]
    # 大小写不敏感匹配
    lower = field_name.lower()
    for k, v in DEFAULT_FIELD_CLASSIFICATION.items():
        if k.lower() == lower:
            return v
    return DataSensitivity.INTERNAL


# ===== 脱敏 =====


def mask_id_card(value: str) -> str:
    """身份证脱敏: 保留前 4 + 后 4, 中间 *."""

    if not value:
        return value
    s = str(value)
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}{'*' * (len(s) - 8)}{s[-4:]}"


def mask_phone(value: str) -> str:
    """手机号脱敏: 138****1234."""
    if not value:
        return value
    s = str(value)
    # 提取数字部分
    digits = re.sub(r"\D", "", s)
    if len(digits) < 7:
        return "*" * len(s)
    # 保留前 3 + *** + 后 4
    return f"{digits[:3]}****{digits[-4:]}"


def mask_bank_card(value: str) -> str:
    """银行卡脱敏: 保留前 4 + 后 4."""
    if not value:
        return value
    s = str(value)
    digits = re.sub(r"\D", "", s)
    if len(digits) <= 8:
        return "*" * len(s)
    return f"{digits[:4]} **** **** {digits[-4:]}"


def mask_email(value: str) -> str:
    """邮箱脱敏: a***@example.com."""
    if not value:
        return value
    s = str(value)
    if "@" not in s:
        return s
    local, domain = s.split("@", 1)
    if len(local) <= 1:
        return s
    return f"{local[0]}***@{domain}"


# 默认按字段名路由脱敏函数
_MASKERS: dict[DataSensitivity, Any] = {
    DataSensitivity.HIGHLY_SENSITIVE: mask_id_card,
    DataSensitivity.SENSITIVE: mask_phone,
}


def mask_value(field_name: str, value: Any) -> str:
    """对单字段值脱敏 (Phase 5 B24 验收).

    路由逻辑:
    - HIGHLY_SENSITIVE → mask_id_card (兼容身份证/银行卡/护照)
    - SENSITIVE → 按字段名细分 (phone / email / address 各有规则)
    - INTERNAL / PUBLIC → 原样返回

    Returns:
        脱敏后字符串 (空字符串 / None 同样返回原值).
    """
    if value is None:
        return ""
    sensitivity = classify_field(field_name)
    if sensitivity == DataSensitivity.PUBLIC:
        return str(value)
    if sensitivity == DataSensitivity.INTERNAL:
        # 内部字段也保留原值 (仅日志用 hash)
        return str(value)

    # sensitive / highly_sensitive 字段细分处理
    lower = field_name.lower()
    # 身份证优先 (避免被 "id_card" 中的 "card" 路由到 bank)
    if (
        "id_card" in lower
        or "id_number" in lower
        or "idcard" in lower
        or "身份证" in field_name
    ):
        return mask_id_card(str(value))
    if "passport" in lower or "护照" in field_name or "cvv" in lower or "social_security" in lower:
        return mask_id_card(str(value))  # 同样按前 N + 后 N 处理
    if "email" in lower or "邮箱" in field_name:
        return mask_email(str(value))
    if (
        "bank_card" in lower
        or "credit_card" in lower
        or "银行卡" in field_name
        or "信用卡" in field_name
    ):
        return mask_bank_card(str(value))
    if "phone" in lower or "mobile" in lower or "手机" in field_name:
        return mask_phone(str(value))

    # 默认按 sensitivity 路由
    masker = _MASKERS.get(sensitivity, mask_id_card)
    return masker(str(value))


# ===== 日志 Hash =====


def hash_value(value: Any, *, length: int = 12) -> str:
    """敏感值日志用 hash (Phase 5 B24 验收).

    SHA256 截断 N 位, 不可逆. 用于审计日志记录"哪个值被读过"但不泄露明文.

    Args:
        value: 原始值.
        length: 输出 hex 字符数 (默认 12 = 48 bits).

    Returns:
        截断的 hex 字符串.
    """
    if value is None:
        return ""
    s = str(value)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:length]


# ===== 递归清洗 =====


def redact_payload(
    payload: dict[str, Any] | list[Any] | Any,
    *,
    sensitivity_threshold: DataSensitivity = DataSensitivity.SENSITIVE,
) -> Any:
    """递归清洗 dict / list 中的敏感字段 (Phase 5 B24 验收).

    Args:
        payload: 待清洗数据 (dict / list / 标量).
        sensitivity_threshold: 阈值, ≥ 该敏感度的字段将被脱敏.
                              默认 SENSITIVE (即 SENSITIVE + HIGHLY_SENSITIVE 都脱敏).

    Returns:
        清洗后数据 (结构与原数据一致).
    """
    if isinstance(payload, dict):
        result: dict[str, Any] = {}
        for k, v in payload.items():
            sensitivity = classify_field(k)
            if (
                _sensitivity_rank(sensitivity) >= _sensitivity_rank(sensitivity_threshold)
                and not isinstance(v, (dict, list))
            ):
                # 标量值脱敏
                result[k] = mask_value(k, v)
            else:
                result[k] = redact_payload(v, sensitivity_threshold=sensitivity_threshold)
        return result
    if isinstance(payload, list):
        return [
            redact_payload(item, sensitivity_threshold=sensitivity_threshold) for item in payload
        ]
    return payload


_SENSITIVITY_RANK: dict[DataSensitivity, int] = {
    DataSensitivity.PUBLIC: 0,
    DataSensitivity.INTERNAL: 1,
    DataSensitivity.SENSITIVE: 2,
    DataSensitivity.HIGHLY_SENSITIVE: 3,
}


def _sensitivity_rank(s: DataSensitivity) -> int:
    return _SENSITIVITY_RANK[s]


__all__ = [
    "DEFAULT_FIELD_CLASSIFICATION",
    "DataSensitivity",
    "classify_field",
    "hash_value",
    "mask_bank_card",
    "mask_email",
    "mask_id_card",
    "mask_phone",
    "mask_value",
    "redact_payload",
]
