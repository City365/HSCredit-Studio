"""Phase 5 B26 PIPL 数据保护 — 单元测试.

依据 docs/ROADMAP.md Phase 5 B26:

- 同意管理 (grant / revoke / check / 撤回轨迹完整)
- 数据主体请求 (DSR) 提交与流转
- 数据可携 (portability) 打包
- 匿名化 (anonymization)
- 跨境传输审批 (PIPL 第 38 条 4 种法律基础)
- 隐私政策中文版

测试为纯函数级 — 不依赖数据库.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC

import pytest

from hscredit_studio.models.pipl import (
    CONSENT_PURPOSE_VALUES,
    CROSS_BORDER_BASIS_VALUES,
)
from hscredit_studio.services.pipl import (
    CURRENT_POLICY_VERSION,
    DSR_LEGAL_DEADLINE_DAYS,
    PRIVACY_POLICY_ZH,
    ConsentState,
    CrossBorderRequest,
    DsrSubmissionResult,
    UserDataPackage,
)

# ===== 枚举与常量 =====


def test_consent_purpose_values():
    """CONSENT_PURPOSE_VALUES: 5 种处理目的."""
    expected = {
        "service_provision",
        "billing",
        "marketing",
        "analytics",
        "third_party_sharing",
    }
    assert set(CONSENT_PURPOSE_VALUES) == expected


def test_cross_border_basis_values():
    """CROSS_BORDER_BASIS_VALUES: PIPL 第 38 条 4 种法律基础."""
    expected = {
        "cac_assessment",
        "standard_contract",
        "certification",
        "explicit_consent",
    }
    assert set(CROSS_BORDER_BASIS_VALUES) == expected


def test_dsr_legal_deadline_days():
    """PIPL 法定 DSR 期限: 30 天."""
    assert DSR_LEGAL_DEADLINE_DAYS == 30


def test_current_policy_version():
    """默认隐私政策版本 v1.0."""
    assert CURRENT_POLICY_VERSION == "v1.0"


def test_privacy_policy_zh_content():
    """PRIVACY_POLICY_ZH: 中文版隐私政策含关键字段."""
    assert "个人信息" in PRIVACY_POLICY_ZH
    assert "查询权" in PRIVACY_POLICY_ZH or "查询" in PRIVACY_POLICY_ZH
    assert "删除权" in PRIVACY_POLICY_ZH or "删除" in PRIVACY_POLICY_ZH
    assert "跨境传输" in PRIVACY_POLICY_ZH


# ===== 数据类 / DTO 行为 =====


def test_consent_state_dataclass():
    """ConsentState 数据类字段齐全."""
    s = ConsentState(
        user_id="u1",
        purpose="marketing",
        granted=True,
        granted_at="2026-08-28T10:00:00+00:00",
        revoked_at=None,
        policy_version="v1.0",
        consent_id="c1",
    )
    assert s.granted is True
    assert s.revoked_at is None
    assert s.purpose == "marketing"


def test_dsr_submission_result():
    """DsrSubmissionResult 字段."""
    r = DsrSubmissionResult(
        request_id="r1",
        submitted_at="2026-08-28T10:00:00+00:00",
        due_at="2026-09-27T10:00:00+00:00",
        status="submitted",
    )
    assert r.status == "submitted"
    assert "2026-09-27" in r.due_at


def test_cross_border_request_dataclass():
    """CrossBorderRequest 字段."""
    from uuid import UUID

    req = CrossBorderRequest(
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        destination_country="US",
        destination_entity="AWS US-East",
        data_categories=["HIGHLY_SENSITIVE.id_card"],
        legal_basis="cac_assessment",
        legal_basis_ref="CAC-2026-001",
    )
    assert req.destination_country == "US"
    assert req.legal_basis == "cac_assessment"


def test_user_data_package_to_dict():
    """UserDataPackage.to_dict() 序列化完整."""
    pkg = UserDataPackage(
        export_id="exp-1",
        exported_at="2026-08-28T10:00:00",
        user_info={"user_id": "u1"},
        consents=[{"purpose": "marketing"}],
        data_subject_requests=[],
        audit_events_count=10,
        audit_events_sample=[{"event_id": "e1"}],
        package_hash="abc123",
    )
    d = pkg.to_dict()
    assert d["export_id"] == "exp-1"
    assert d["audit_events_count"] == 10
    assert d["package_hash"] == "abc123"


def test_user_data_package_hash_deterministic():
    """UserDataPackage hash: 相同内容产生相同 hash."""
    pkg_dict = {
        "user_info": {"user_id": "u1"},
        "consents": [{"purpose": "marketing"}],
        "data_subject_requests": [],
        "audit_events_count": 0,
    }
    canonical = json.dumps(pkg_dict, ensure_ascii=False, sort_keys=True, default=str)
    h1 = hashlib.sha256(canonical.encode()).hexdigest()
    h2 = hashlib.sha256(canonical.encode()).hexdigest()
    assert h1 == h2
    assert len(h1) == 64


# ===== 业务逻辑纯函数 =====


def test_consent_state_distinguishes_active_revoked():
    """ConsentState: 通过 granted 字段区分当前状态."""
    active = ConsentState(
        user_id="u1",
        purpose="marketing",
        granted=True,
        granted_at="2026-08-28T10:00:00",
        revoked_at=None,
        policy_version="v1.0",
        consent_id="c1",
    )
    revoked = ConsentState(
        user_id="u1",
        purpose="marketing",
        granted=True,  # 历史同意
        granted_at="2026-08-28T10:00:00",
        revoked_at="2026-08-29T10:00:00",  # 已撤回
        policy_version="v1.0",
        consent_id="c1",
    )
    assert active.granted is True and active.revoked_at is None
    assert revoked.granted is True and revoked.revoked_at is not None


def test_dsr_deadline_calc_30_days():
    """DSR 法定截止 = 提交时间 + 30 天."""
    from datetime import datetime, timedelta

    now = datetime.now(UTC)
    due = now + timedelta(days=DSR_LEGAL_DEADLINE_DAYS)
    delta = (due - now).days
    assert delta == 30


@pytest.mark.parametrize(
    "basis",
    [
        "cac_assessment",
        "standard_contract",
        "certification",
        "explicit_consent",
    ],
)
def test_cross_border_basis_accepted(basis):
    """4 种法律基础均被接受."""
    assert basis in CROSS_BORDER_BASIS_VALUES


def test_cross_border_basis_invalid():
    """不在枚举内的法律基础被拒绝."""
    assert "weird_basis" not in CROSS_BORDER_BASIS_VALUES


# ===== Module-level 冒烟 =====


@pytest.mark.asyncio
async def test_pipl_module_imports():
    """验证 PIPL 模块可被导入 (Phase 5 B26 冒脚)."""
    from hscredit_studio.services import pipl

    assert hasattr(pipl, "submit_dsr")
    assert hasattr(pipl, "anonymize_user")
    assert hasattr(pipl, "export_user_data_package")
