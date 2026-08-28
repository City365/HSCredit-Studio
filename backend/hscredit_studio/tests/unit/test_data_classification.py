"""Phase 5 B24 数据分类与脱敏 — 单元测试.

依据 docs/ROADMAP.md Phase 5 B24 验收:

- DataSensitivity: 4 级枚举 (PUBLIC/INTERNAL/SENSITIVE/HIGHLY_SENSITIVE)
- DEFAULT_FIELD_CLASSIFICATION: 25+ 预置字段映射
- classify_field: 字段名查分级
- mask_value: 身份证/手机号/邮箱/银行卡 各有规则
- hash_value: SHA256 截断 (不可逆)
- redact_payload: 递归清洗 dict/list
"""
from __future__ import annotations

from hscredit_studio.services.data_classification import (
    DEFAULT_FIELD_CLASSIFICATION,
    DataSensitivity,
    classify_field,
    hash_value,
    mask_bank_card,
    mask_email,
    mask_id_card,
    mask_phone,
    mask_value,
    redact_payload,
)

# ===== 枚举与映射测试 =====


def test_data_sensitivity_enum():
    """DataSensitivity: 4 级枚举."""
    assert DataSensitivity.PUBLIC == "public"
    assert DataSensitivity.INTERNAL == "internal"
    assert DataSensitivity.SENSITIVE == "sensitive"
    assert DataSensitivity.HIGHLY_SENSITIVE == "highly_sensitive"


def test_default_field_classification_size():
    """DEFAULT_FIELD_CLASSIFICATION: 至少 20 个预置字段."""
    assert len(DEFAULT_FIELD_CLASSIFICATION) >= 20


def test_default_field_classification_has_highly_sensitive():
    """DEFAULT_FIELD_CLASSIFICATION: 含高敏字段 (身份证/银行卡)."""
    assert DEFAULT_FIELD_CLASSIFICATION[("id_card")] == DataSensitivity.HIGHLY_SENSITIVE
    assert DEFAULT_FIELD_CLASSIFICATION[("bank_card")] == DataSensitivity.HIGHLY_SENSITIVE
    assert DEFAULT_FIELD_CLASSIFICATION[("身份证")] == DataSensitivity.HIGHLY_SENSITIVE


def test_default_field_classification_has_sensitive():
    """DEFAULT_FIELD_CLASSIFICATION: 含敏感字段 (手机/邮箱)."""
    assert DEFAULT_FIELD_CLASSIFICATION[("phone")] == DataSensitivity.SENSITIVE
    assert DEFAULT_FIELD_CLASSIFICATION[("email")] == DataSensitivity.SENSITIVE


def test_default_field_classification_has_public():
    """DEFAULT_FIELD_CLASSIFICATION: 含公开字段 (id/name/status)."""
    assert DEFAULT_FIELD_CLASSIFICATION[("id")] == DataSensitivity.PUBLIC
    assert DEFAULT_FIELD_CLASSIFICATION[("name")] == DataSensitivity.PUBLIC
    assert DEFAULT_FIELD_CLASSIFICATION[("status")] == DataSensitivity.PUBLIC


def test_classify_field_known():
    """classify_field: 已知字段正确分级."""
    assert classify_field("id_card") == DataSensitivity.HIGHLY_SENSITIVE
    assert classify_field("phone") == DataSensitivity.SENSITIVE
    assert classify_field("id") == DataSensitivity.PUBLIC


def test_classify_field_case_insensitive():
    """classify_field: 大小写不敏感."""
    assert classify_field("ID_CARD") == DataSensitivity.HIGHLY_SENSITIVE
    assert classify_field("Phone") == DataSensitivity.SENSITIVE


def test_classify_field_unknown_defaults_to_internal():
    """classify_field: 未知字段默认 INTERNAL (保守)."""
    assert classify_field("xyz_unknown_field") == DataSensitivity.INTERNAL


# ===== mask_xxx 函数测试 =====


def test_mask_id_card():
    """mask_id_card: 保留前 4 + 后 4."""
    assert mask_id_card("110101199001011234") == "1101**********1234"
    assert mask_id_card("12345") == "*****"
    assert mask_id_card("") == ""
    assert mask_id_card(None) is None


def test_mask_phone():
    """mask_phone: 138****1234."""
    assert mask_phone("13800138000") == "138****8000"
    assert mask_phone("12345") == "*****"
    assert mask_phone("") == ""


def test_mask_email():
    """mask_email: a***@example.com."""
    assert mask_email("alice@example.com") == "a***@example.com"
    assert mask_email("bob@x.io") == "b***@x.io"
    # 单字符 local 保持原样 (避免 a***@ 仅剩 a 反而泄露更多)
    assert mask_email("a@x.io") == "a@x.io"


def test_mask_bank_card():
    """mask_bank_card: 6222 **** **** 1234."""
    assert mask_bank_card("6222601234561234") == "6222 **** **** 1234"
    assert mask_bank_card("12345678") == "********"


def test_mask_value_routes_by_field_name():
    """mask_value: 字段名路由对应 masker."""
    # 身份证 → id_card masker (保留前4+后4)
    assert mask_value("id_card", "110101199001011234") == "1101**********1234"
    # 手机号 → phone masker
    assert mask_value("phone", "13800138000") == "138****8000"
    # 邮箱 → email masker
    assert mask_value("email", "alice@example.com") == "a***@example.com"
    # 银行卡 → bank_card masker (bank 字段路由)
    assert mask_value("bank_card", "6222601234561234") == "6222 **** **** 1234"
    # id_number 走 id_card masker
    assert mask_value("id_number", "110101199003031234") == "1101**********1234"


def test_mask_value_public_unchanged():
    """mask_value: 公开字段原样返回."""
    assert mask_value("name", "张三") == "张三"
    assert mask_value("status", "active") == "active"


def test_mask_value_internal_unchanged():
    """mask_value: 内部字段原样返回 (仅日志 hash)."""
    assert mask_value("tenant_id", "abc-123") == "abc-123"


def test_mask_value_none_returns_empty_string():
    """mask_value: None 值返回空字符串."""
    assert mask_value("phone", None) == ""


# ===== hash_value 测试 =====


def test_hash_value_consistent():
    """hash_value: 相同输入返回相同 hash (SHA256 确定性)."""
    h1 = hash_value("13800138000")
    h2 = hash_value("13800138000")
    assert h1 == h2


def test_hash_value_different_input():
    """hash_value: 不同输入返回不同 hash."""
    assert hash_value("13800138000") != hash_value("13800138999")


def test_hash_value_length():
    """hash_value: 默认 12 位 hex 截断."""
    h = hash_value("test")
    assert len(h) == 12
    # 自定义长度
    assert len(hash_value("test", length=20)) == 20


def test_hash_value_none_returns_empty():
    """hash_value: None 返回空字符串."""
    assert hash_value(None) == ""


def test_hash_value_irreversible():
    """hash_value: 不能从 hash 反推明文 (文档属性)."""
    # SHA256 单向性, 此测试仅文档化
    assert hash_value("secret") == hash_value("secret")


# ===== redact_payload 测试 =====


def test_redact_payload_dict():
    """redact_payload: dict 中的敏感字段被脱敏."""
    payload = {
        "id": "abc-123",
        "name": "张三",
        "phone": "13800138000",
        "email": "alice@example.com",
        "id_card": "110101199001011234",
    }
    redacted = redact_payload(payload)
    assert redacted["id"] == "abc-123"
    assert redacted["name"] == "张三"
    assert redacted["phone"] == "138****8000"
    assert redacted["email"] == "a***@example.com"
    assert "1234" in redacted["id_card"]
    assert redacted["id_card"] != "110101199001011234"


def test_redact_payload_nested():
    """redact_payload: 嵌套 dict 递归脱敏."""
    payload = {
        "user_id": "u-1",
        "profile": {
            "name": "李四",
            "phone": "13800138001",
            "id_card": "110101199002021234",
        },
    }
    redacted = redact_payload(payload)
    assert redacted["user_id"] == "u-1"  # INTERNAL 保留
    assert redacted["profile"]["name"] == "李四"
    assert redacted["profile"]["phone"] == "138****8001"
    assert redacted["profile"]["id_card"] != "110101199002021234"


def test_redact_payload_list():
    """redact_payload: list 中每个 dict 都脱敏."""
    payload = [
        {"name": "A", "phone": "13800138001"},
        {"name": "B", "phone": "13800138002"},
    ]
    redacted = redact_payload(payload)
    assert redacted[0]["phone"] == "138****8001"
    assert redacted[1]["phone"] == "138****8002"


def test_redact_payload_threshold_public():
    """redact_payload: threshold=PUBLIC 时 (无意义, 但不应报错)."""
    payload = {"name": "x", "phone": "13800138000"}
    # threshold=PUBLIC (rank=0) → 所有 >= 0 都脱敏, 实际会脱敏所有字段
    redacted = redact_payload(payload, sensitivity_threshold=DataSensitivity.PUBLIC)
    assert redacted["name"] == "x"  # PUBLIC 不脱敏 (rank==threshold 不算 >=)
    # 实际: PUBLIC 字段 rank==threshold, 不算 >=, 不脱敏
    # 而 phone (SENSITIVE) rank=2 > 0, 会脱敏
    assert redacted["phone"] == "138****8000"


def test_redact_payload_threshold_highly_sensitive():
    """redact_payload: threshold=HIGHLY_SENSITIVE 时仅脱敏高敏字段."""
    payload = {"id_card": "110101199001011234", "phone": "13800138000"}
    redacted = redact_payload(payload, sensitivity_threshold=DataSensitivity.HIGHLY_SENSITIVE)
    assert "1234" in redacted["id_card"]  # 脱敏
    assert redacted["phone"] == "13800138000"  # 不脱敏 (SENSITIVE < HIGHLY_SENSITIVE)


def test_redact_payload_empty_dict():
    """redact_payload: 空 dict."""
    assert redact_payload({}) == {}


def test_redact_payload_scalar_passthrough():
    """redact_payload: 标量原样返回."""
    assert redact_payload("plain string") == "plain string"
    assert redact_payload(42) == 42
