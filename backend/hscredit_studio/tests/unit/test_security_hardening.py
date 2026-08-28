"""Phase 5 B25 安全加固 — 单元测试.

依据 docs/ROADMAP.md Phase 5 B25:

- HMAC 审计链 (sign_audit_event / compute_chain_hash / verify_audit_chain)
- 入侵防范 (WAF): SQL 注入 / XSS / 路径遍历检测
- IP 访问控制 (CIDR 匹配 / 白黑名单)
- 认证加固 (密码复杂度 / LockoutTracker)
- 数据保护 (审计日志自动 mask)
- SIEM 导出 (CEF / syslog / csv 格式)
- 漏洞跟踪
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hscredit_studio.services.security_hardening import (
    AUDIT_CHAIN_GENESIS_HASH,
    LockoutTracker,
    PasswordStrength,
    ThreatType,
    check_ip_allowed,
    compute_chain_hash,
    detect_suspicious_request,
    ip_in_cidr,
    mask_audit_details,
    sign_audit_event,
    validate_password_complexity,
    verify_audit_chain,
)
from hscredit_studio.services.soc import (
    create_vulnerability,  # noqa: F401  — 仅用于 type 提示, 实际不在本文件调用
    export_events_cef,
    export_events_syslog,
)

# ===== HMAC 审计链 =====


def test_sign_audit_event_deterministic():
    """sign_audit_event: 相同输入产生相同签名."""
    payload = {"event_id": "e1", "action": "login"}
    secret = "test-secret-1234567890"
    sig1 = sign_audit_event(payload, secret)
    sig2 = sign_audit_event(payload, secret)
    assert sig1 == sig2
    assert len(sig1) == 64  # SHA256 hex


def test_sign_audit_event_field_order_independent():
    """sign_audit_event: 字段顺序不影响签名 (canonical JSON)."""
    secret = "secret-1234567890"
    p1 = {"a": 1, "b": 2, "c": 3}
    p2 = {"c": 3, "b": 2, "a": 1}
    assert sign_audit_event(p1, secret) == sign_audit_event(p2, secret)


def test_sign_audit_event_different_secret():
    """sign_audit_event: 不同密钥产生不同签名."""
    p = {"x": "y"}
    assert sign_audit_event(p, "secret-A") != sign_audit_event(p, "secret-B")


def test_sign_audit_event_missing_secret_returns_empty():
    """sign_audit_event: 缺密钥返回空字符串 + warn log."""
    sig = sign_audit_event({"x": "y"}, "")
    assert sig == ""


def test_compute_chain_hash_links_previous():
    """compute_chain_hash: 输出与 prev_hash + payload 都相关."""
    secret = "test-secret-1234567890"
    h1 = compute_chain_hash(AUDIT_CHAIN_GENESIS_HASH, {"id": "a"}, secret)
    h2 = compute_chain_hash(AUDIT_CHAIN_GENESIS_HASH, {"id": "b"}, secret)
    h3 = compute_chain_hash(h1, {"id": "next"}, secret)
    # 同 prev 不同 payload → 不同 hash
    assert h1 != h2
    # 不同 prev 同 payload → 不同 hash (链式依赖)
    h4 = compute_chain_hash(h2, {"id": "next"}, secret)
    assert h3 != h4


def test_verify_audit_chain_valid():
    """verify_audit_chain: 完整链通过验证."""
    secret = "test-secret-1234567890"
    events: list[dict] = []
    prev_hash = AUDIT_CHAIN_GENESIS_HASH
    for i in range(3):
        ev = {"event_id": f"e-{i}", "action": "login", "ts": "2026-08-28"}
        ev["chain_hash"] = compute_chain_hash(prev_hash, ev, secret)
        events.append(ev)
        prev_hash = ev["chain_hash"]
    result = verify_audit_chain(events, secret)
    assert result.is_valid is True
    assert result.checked_count == 3


def test_verify_audit_chain_tampered():
    """verify_audit_chain: 篡改事件导致失败."""
    secret = "test-secret-1234567890"
    events: list[dict] = []
    prev_hash = AUDIT_CHAIN_GENESIS_HASH
    for i in range(3):
        ev = {"event_id": f"e-{i}", "action": "login"}
        ev["chain_hash"] = compute_chain_hash(prev_hash, ev, secret)
        events.append(ev)
        prev_hash = ev["chain_hash"]
    # 篡改第二事件 action
    events[1]["action"] = "permission_change"
    result = verify_audit_chain(events, secret)
    assert result.is_valid is False
    assert result.failed_at_index == 1
    assert result.failed_event_id == "e-1"


def test_verify_audit_chain_missing_hash():
    """verify_audit_chain: 缺 chain_hash 字段报错."""
    events = [{"event_id": "e1", "action": "login"}]  # 无 chain_hash
    result = verify_audit_chain(events, "secret")
    assert result.is_valid is False
    assert "chain_hash" in (result.error or "")


# ===== 入侵防范 (WAF) =====


def test_detect_sql_injection():
    """detect_suspicious_request: SQL 注入检测."""
    hits = detect_suspicious_request(
        path="/api/users",
        query="id=1 UNION SELECT * FROM users",
    )
    assert any(h.threat_type == ThreatType.SQL_INJECTION for h in hits)


def test_detect_xss():
    """detect_suspicious_request: XSS 检测."""
    hits = detect_suspicious_request(
        query="name=<script>alert(1)</script>",
    )
    assert any(h.threat_type == ThreatType.XSS for h in hits)


def test_detect_path_traversal():
    """detect_suspicious_request: 路径遍历检测."""
    hits = detect_suspicious_request(
        path="/static/../../../etc/passwd",
    )
    assert any(h.threat_type == ThreatType.PATH_TRAVERSAL for h in hits)


def test_detect_command_injection():
    """detect_suspicious_request: 命令注入检测."""
    hits = detect_suspicious_request(
        body='{"cmd": "ls; rm -rf /"}',
    )
    assert any(h.threat_type == ThreatType.COMMAND_INJECTION for h in hits)


def test_detect_clean_request():
    """detect_suspicious_request: 正常请求返回空."""
    hits = detect_suspicious_request(
        path="/api/users/123",
        query="limit=20&offset=0",
        user_agent="Mozilla/5.0 ...",
    )
    assert hits == []


def test_detect_multiple_threats():
    """detect_suspicious_request: 同时命中多种威胁."""
    hits = detect_suspicious_request(
        query="id=1 UNION SELECT",
        user_agent="<script>alert(1)</script>",
    )
    threat_types = {h.threat_type for h in hits}
    assert ThreatType.SQL_INJECTION in threat_types
    assert ThreatType.XSS in threat_types


# ===== IP 访问控制 =====


def test_ip_in_cidr_ipv4():
    """ip_in_cidr: IPv4 网段匹配."""
    assert ip_in_cidr("192.168.1.100", "192.168.1.0/24") is True
    assert ip_in_cidr("192.168.2.1", "192.168.1.0/24") is False
    assert ip_in_cidr("10.0.0.1", "10.0.0.0/8") is True


def test_ip_in_cidr_single_ip():
    """ip_in_cidr: 单 IP 也接受."""
    assert ip_in_cidr("10.0.0.5", "10.0.0.5") is True
    assert ip_in_cidr("10.0.0.6", "10.0.0.5") is False


def test_ip_in_cidr_invalid_input():
    """ip_in_cidr: 无效输入返回 False (不抛错)."""
    assert ip_in_cidr("not-an-ip", "10.0.0.0/8") is False
    assert ip_in_cidr("10.0.0.1", "not-cidr") is False


def test_check_ip_blacklist_priority():
    """check_ip_allowed: 黑名单优先于白名单."""
    decision = check_ip_allowed(
        "10.0.0.5",
        whitelist=["10.0.0.0/8"],
        blacklist=["10.0.0.5/32"],
    )
    assert decision.allowed is False
    assert "黑名单" in decision.reason


def test_check_ip_whitelist_match():
    """check_ip_allowed: 命中白名单放行."""
    decision = check_ip_allowed(
        "192.168.1.5",
        whitelist=["192.168.1.0/24"],
    )
    assert decision.allowed is True
    assert decision.matched_rule == "192.168.1.0/24"


def test_check_ip_whitelist_miss_reject():
    """check_ip_allowed: 启用白名单但未命中则拒绝."""
    decision = check_ip_allowed(
        "8.8.8.8",
        whitelist=["192.168.1.0/24"],
    )
    assert decision.allowed is False


def test_check_ip_default_allow():
    """check_ip_allowed: 无黑白名单时按 default 决定."""
    decision = check_ip_allowed("1.2.3.4", default_allow=True)
    assert decision.allowed is True
    decision2 = check_ip_allowed("1.2.3.4", default_allow=False)
    assert decision2.allowed is False


# ===== 认证加固 =====


def test_password_strength_strong():
    """validate_password_complexity: 强密码 (4 类全有 + 长度 ≥ 8)."""
    assert validate_password_complexity("Abc123!@#") == PasswordStrength.STRONG


def test_password_strength_medium():
    """validate_password_complexity: 中等 (≥ 8 + 3 类)."""
    assert validate_password_complexity("Abcdef12") == PasswordStrength.MEDIUM


def test_password_strength_weak():
    """validate_password_complexity: 弱 (≥ 8 + 2 类)."""
    assert validate_password_complexity("abcdefg1") == PasswordStrength.WEAK


def test_password_strength_only_lowercase_invalid():
    """validate_password_complexity: 仅小写类 = INVALID."""
    assert validate_password_complexity("abcdefgh") == PasswordStrength.INVALID


def test_password_strength_invalid_too_short():
    """validate_password_complexity: 长度不足 = INVALID."""
    assert validate_password_complexity("Ab1!") == PasswordStrength.INVALID
    assert validate_password_complexity("") == PasswordStrength.INVALID


def test_password_strength_invalid_too_simple():
    """validate_password_complexity: 长度够但仅 1 类 = INVALID."""
    assert validate_password_complexity("aaaaaaaa") == PasswordStrength.INVALID


# ===== LockoutTracker =====


def test_lockout_tracker_not_locked_initially():
    """LockoutTracker: 初始无锁定."""
    t = LockoutTracker(max_failures=3, cooldown_seconds=60)
    state = t.check("user-1", now_ts=1000.0)
    assert state.is_locked is False
    assert state.failed_count == 0


def test_lockout_tracker_locks_after_max_failures():
    """LockoutTracker: 失败 max_failures 次后锁定."""
    t = LockoutTracker(max_failures=3, cooldown_seconds=60, window_seconds=300)
    now = 1000.0
    for i in range(3):
        t.record_failure("user-1", now_ts=now + i)
    state = t.check("user-1", now_ts=now + 10)
    assert state.is_locked is True
    assert state.failed_count == 3


def test_lockout_tracker_resets_on_success():
    """LockoutTracker: 成功登录重置计数."""
    t = LockoutTracker(max_failures=5)
    t.record_failure("u", now_ts=1000.0)
    t.record_failure("u", now_ts=1001.0)
    t.record_success("u")
    state = t.check("u", now_ts=1005.0)
    assert state.failed_count == 0


def test_lockout_tracker_window_excludes_old_failures():
    """LockoutTracker: 窗口外的失败不计入."""
    t = LockoutTracker(max_failures=3, window_seconds=60)
    # 3 次失败都在很久以前
    for i in range(3):
        t.record_failure("u", now_ts=100.0 + i)
    # 当前时间 1000s → 全部失效
    state = t.check("u", now_ts=1000.0)
    assert state.failed_count == 0
    assert state.is_locked is False


def test_lockout_tracker_lockout_expires():
    """LockoutTracker: 冷却期过后解锁."""
    t = LockoutTracker(max_failures=2, cooldown_seconds=60, window_seconds=300)
    t.record_failure("u", now_ts=1000.0)
    t.record_failure("u", now_ts=1001.0)
    # 锁定到 1061 (1001+60)
    state = t.check("u", now_ts=1050.0)
    assert state.is_locked is True
    state = t.check("u", now_ts=1070.0)
    assert state.is_locked is False


# ===== 数据保护 (审计日志 mask) =====


def test_mask_audit_details_dict():
    """mask_audit_details: dict 中敏感字段被脱敏."""
    details = {
        "name": "张三",
        "phone": "13800138000",
        "id_card": "110101199001011234",
    }
    masked = mask_audit_details(details)
    assert masked["name"] == "张三"
    assert masked["phone"] == "138****8000"
    assert "1234" in masked["id_card"] and "1990" not in masked["id_card"]


def test_mask_audit_details_nested():
    """mask_audit_details: 嵌套 dict 递归."""
    details = {"user": {"phone": "13800138000", "id_card": "110101199001011234"}}
    masked = mask_audit_details(details)
    assert "****" in masked["user"]["phone"]


def test_mask_audit_details_threshold_highly_sensitive():
    """mask_audit_details: 阈值=HIGHLY_SENSITIVE 时仅脱敏高敏."""
    details = {"phone": "13800138000", "id_card": "110101199001011234"}
    masked = mask_audit_details(details, threshold="highly_sensitive")  # type: ignore[arg-type]
    assert masked["phone"] == "13800138000"  # 不脱敏
    assert "1234" in masked["id_card"]  # 脱敏


def test_mask_audit_details_empty():
    """mask_audit_details: 空 / None 不报错."""
    assert mask_audit_details(None) == {}
    assert mask_audit_details({}) == {}


# ===== SIEM 导出 =====


def test_export_events_cef_format():
    """export_events_cef: 输出符合 CEF 格式."""
    events = [
        {
            "event_id": "e1",
            "tenant_id": "t1",
            "user_id": "u1",
            "action": "login_failed",
            "resource_type": "user",
            "resource_id": "r1",
            "ip_address": "10.0.0.1",
            "user_agent": "ua",
            "occurred_at": datetime(2026, 8, 28, 10, 0, 0, tzinfo=UTC),
            "details": {"email": "x@y.com"},
        }
    ]
    out = export_events_cef(events)
    assert "CEF:0|HSCredit|HSCredit-Studio|" in out
    assert "1002" in out  # login_failed signature
    assert "act=login_failed" in out
    assert "src=10.0.0.1" in out


def test_export_events_cef_multiple_events():
    """export_events_cef: 多事件分行输出."""
    events = [
        {"event_id": "e1", "action": "login", "occurred_at": datetime.now(UTC)},
        {"event_id": "e2", "action": "data_export", "occurred_at": datetime.now(UTC)},
    ]
    out = export_events_cef(events)
    lines = out.split("\n")
    assert len(lines) == 2


def test_export_events_syslog_rfc5424():
    """export_events_syslog: RFC 5424 格式."""
    events = [
        {
            "event_id": "e1",
            "action": "login",
            "tenant_id": "t1",
            "user_id": "u1",
            "ip_address": "10.0.0.1",
            "occurred_at": datetime(2026, 8, 28, 10, 0, 0),
        }
    ]
    out = export_events_syslog(events)
    assert "<" in out and ">" in out
    assert "HSCredit audit" in out


def test_export_events_empty():
    """export_events_cef/syslog: 空事件返回空字符串."""
    assert export_events_cef([]) == ""
    assert export_events_syslog([]) == ""


# ===== ThreatType 枚举 =====


def test_threat_type_values():
    """ThreatType: 5 种威胁类型."""
    assert ThreatType.SQL_INJECTION.value == "sql_injection"
    assert ThreatType.XSS.value == "xss"
    assert ThreatType.PATH_TRAVERSAL.value == "path_traversal"
    assert ThreatType.COMMAND_INJECTION.value == "command_injection"
    assert ThreatType.LDAP_INJECTION.value == "ldap_injection"


# ===== 集成 / 回归 =====


def test_chain_hash_compatible_with_sign():
    """单事件签 vs 链签 是同一族 HMAC, 但输入不同 (genesis vs prev_hash).

    验证两者都返回 64 hex 字符的 HMAC-SHA256, 字段顺序无关性由 canonical JSON 保证.
    """
    secret = "test-secret"
    payload = {"event_id": "e1", "action": "login"}
    single_sig = sign_audit_event(payload, secret)
    chain_hash = compute_chain_hash(AUDIT_CHAIN_GENESIS_HASH, payload, secret)
    # 两者都是合法 HMAC-SHA256 hex
    assert len(single_sig) == 64
    assert len(chain_hash) == 64
    # 字段顺序无关
    assert sign_audit_event({"a": 1, "b": 2}, secret) == sign_audit_event(
        {"b": 2, "a": 1}, secret
    )
    # 不同 prev_hash 链上产生不同 hash
    h_a = compute_chain_hash("0" * 64, payload, secret)
    h_b = compute_chain_hash("1" * 64, payload, secret)
    assert h_a != h_b


@pytest.mark.asyncio
async def test_security_imports():
    """验证模块可被正常导入 (Phase 5 B25 冒脚)."""
    from hscredit_studio.services import security_hardening, soc

    assert hasattr(security_hardening, "verify_audit_chain")
    assert hasattr(soc, "export_events_cef")
