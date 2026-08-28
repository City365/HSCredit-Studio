"""Phase 5 B27 Alertmanager 集成 — 单元测试.

依据 docs/ROADMAP.md Phase 5 B27:

- 8+ 内置 Prometheus alert rules
- 4 级 severity → 多通道路由
- 抑制规则 (inhibition)
- 静默规则 (silence 时间窗口 + matcher)
- 告警评估: should_send / channels / receiver
- Prometheus rules.yaml 导出
- Alertmanager config 导出
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hscredit_studio.services.alert_rules import (
    DEFAULT_ALERT_ROUTES,
    DEFAULT_ALERT_RULES,
    INHIBITION_RULES,
    AlertChannel,
    AlertRuleSpec,
    AlertSeverity,
    SilenceRule,
    alertmanager_config_yaml,
    all_rules_to_yaml,
    compute_fingerprint,
    evaluate_alert,
    is_silenced,
    rule_to_prometheus_yaml,
    should_inhibit,
)

# ===== 枚举 / 常量 =====


def test_alert_severity_values():
    """AlertSeverity: 4 级."""
    assert AlertSeverity.INFO == "info"
    assert AlertSeverity.WARNING == "warning"
    assert AlertSeverity.CRITICAL == "critical"
    assert AlertSeverity.PAGE == "page"


def test_alert_channel_values():
    """AlertChannel: 6 通道."""
    assert AlertChannel.EMAIL == "email"
    assert AlertChannel.SLACK == "slack"
    assert AlertChannel.WECOM == "wecom"
    assert AlertChannel.PHONE == "phone"
    assert AlertChannel.SMS == "sms"
    assert AlertChannel.WEBHOOK == "webhook"


def test_default_rules_count():
    """DEFAULT_ALERT_RULES: ≥ 8 条."""
    assert len(DEFAULT_ALERT_RULES) >= 8


def test_default_routes_count():
    """DEFAULT_ALERT_ROUTES: 4 条 (对应 4 个 severity)."""
    assert len(DEFAULT_ALERT_ROUTES) == 4
    severities = {r.match_severity for r in DEFAULT_ALERT_ROUTES}
    assert severities == set(AlertSeverity)


def test_inhibition_rules_present():
    """INHIBITION_RULES: 至少 2 条."""
    assert len(INHIBITION_RULES) >= 2


# ===== fingerprint =====


def test_compute_fingerprint_deterministic():
    """compute_fingerprint: 相同输入产生相同输出."""
    labels = {"severity": "warning", "alertname": "X"}
    assert compute_fingerprint(labels) == compute_fingerprint(labels)


def test_compute_fingerprint_field_order_independent():
    """compute_fingerprint: 字段顺序无关."""
    l1 = {"a": "1", "b": "2"}
    l2 = {"b": "2", "a": "1"}
    assert compute_fingerprint(l1) == compute_fingerprint(l2)


def test_compute_fingerprint_differs():
    """compute_fingerprint: 不同 labels 产生不同指纹."""
    assert compute_fingerprint({"a": "1"}) != compute_fingerprint({"a": "2"})


def test_compute_fingerprint_length():
    """compute_fingerprint: 16 hex 字符."""
    fp = compute_fingerprint({"x": "y"})
    assert len(fp) == 16


# ===== should_inhibit =====


def test_should_inhibit_no_match():
    """should_inhibit: 普通告警不被抑制."""
    inhibited, reason = should_inhibit({"severity": "info", "alertname": "X"})
    assert inhibited is False
    assert reason == ""


def test_should_inhibit_critical_availability():
    """should_inhibit: critical availability 是 source (不抑制自身)."""
    inhibited, _reason = should_inhibit(
        {"severity": "critical", "group": "availability", "alertname": "X"}
    )
    assert inhibited is False  # source 不抑制自身


def test_should_inhibit_warning_performance():
    """should_inhibit: warning performance 被 critical availability 抑制."""
    inhibited, reason = should_inhibit(
        {"severity": "warning", "group": "performance", "alertname": "Y"}
    )
    assert inhibited is True
    assert "上游宕机" in reason or "下游" in reason


# ===== SilenceRule / is_silenced =====


def test_silence_rule_active_window():
    """SilenceRule.is_active: 当前时间在窗口内."""
    now = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)
    rule = SilenceRule(
        silence_id="s1",
        matchers={"severity": "warning"},
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=1),
    )
    assert rule.is_active(now) is True
    assert rule.is_active(now + timedelta(hours=2)) is False
    assert rule.is_active(now - timedelta(hours=2)) is False


def test_silence_rule_matches_all_matchers():
    """SilenceRule.matches: 所有 matcher 全匹配才返回 True."""
    rule = SilenceRule(
        silence_id="s1",
        matchers={"severity": "warning", "group": "performance"},
        starts_at=datetime.now(UTC),
        ends_at=datetime.now(UTC) + timedelta(hours=1),
    )
    assert rule.matches({"severity": "warning", "group": "performance"}) is True
    assert rule.matches({"severity": "warning", "group": "database"}) is False
    assert rule.matches({"severity": "critical", "group": "performance"}) is False


def test_is_silenced_active_match():
    """is_silenced: 窗口内匹配返回 True."""
    now = datetime.now(UTC)
    silences = [
        SilenceRule(
            silence_id="s1",
            matchers={"severity": "warning"},
            starts_at=now - timedelta(minutes=10),
            ends_at=now + timedelta(minutes=10),
            comment="E2E 维护窗口",
        )
    ]
    silenced, reason = is_silenced({"severity": "warning"}, silences, now)
    assert silenced is True
    assert "维护窗口" in reason


def test_is_silenced_no_match():
    """is_silenced: matcher 不匹配返回 False."""
    now = datetime.now(UTC)
    silences = [
        SilenceRule(
            silence_id="s1",
            matchers={"severity": "page"},
            starts_at=now - timedelta(minutes=10),
            ends_at=now + timedelta(minutes=10),
        )
    ]
    silenced, _reason = is_silenced({"severity": "warning"}, silences, now)
    assert silenced is False


def test_is_silenced_expired():
    """is_silenced: 已过期静默不再生效."""
    now = datetime.now(UTC)
    silences = [
        SilenceRule(
            silence_id="s1",
            matchers={"severity": "warning"},
            starts_at=now - timedelta(hours=2),
            ends_at=now - timedelta(hours=1),  # 已过期
        )
    ]
    silenced, _ = is_silenced({"severity": "warning"}, silences, now)
    assert silenced is False


# ===== evaluate_alert =====


def test_evaluate_alert_info_routing():
    """evaluate_alert: info → slack."""
    ev = evaluate_alert({"severity": "info", "alertname": "X"})
    assert ev.should_send is True
    assert ev.severity == AlertSeverity.INFO
    assert AlertChannel.SLACK in ev.channels
    assert ev.receiver == "ops-info"


def test_evaluate_alert_warning_routing():
    """evaluate_alert: warning → email + slack (在 specific group 避免被抑制)."""
    ev = evaluate_alert(
        {"severity": "warning", "alertname": "X", "group": "uninhibited_group"}
    )
    assert AlertChannel.EMAIL in ev.channels
    assert AlertChannel.SLACK in ev.channels


def test_evaluate_alert_critical_routing():
    """evaluate_alert: critical → email + slack + wecom."""
    ev = evaluate_alert({"severity": "critical", "alertname": "X"})
    assert AlertChannel.EMAIL in ev.channels
    assert AlertChannel.WECOM in ev.channels


def test_evaluate_alert_page_routing():
    """evaluate_alert: page → phone + sms + wecom."""
    ev = evaluate_alert({"severity": "page", "alertname": "X"})
    assert AlertChannel.PHONE in ev.channels
    assert AlertChannel.SMS in ev.channels
    assert AlertChannel.WECOM in ev.channels


def test_evaluate_alert_inhibited():
    """evaluate_alert: 被抑制时 should_send=False."""
    # warning performance 被 critical availability 抑制
    ev = evaluate_alert(
        {
            "severity": "warning",
            "group": "performance",
            "alertname": "Y",
        }
    )
    assert ev.should_send is False
    assert ev.should_inhibit is True
    assert ev.channels == []


def test_evaluate_alert_silenced():
    """evaluate_alert: 被静默时 should_send=False."""
    now = datetime.now(UTC)
    silences = [
        SilenceRule(
            silence_id="s1",
            matchers={"alertname": "TestAlert"},
            starts_at=now - timedelta(minutes=10),
            ends_at=now + timedelta(minutes=10),
        )
    ]
    ev = evaluate_alert(
        {"severity": "warning", "alertname": "TestAlert"},
        silences=silences,
        now=now,
    )
    assert ev.should_send is False
    assert ev.is_silenced is True
    assert ev.channels == []


def test_evaluate_alert_default_unknown_severity():
    """evaluate_alert: 未知 severity 退到 warning."""
    ev = evaluate_alert({"severity": "weird", "alertname": "X"})
    assert ev.severity == AlertSeverity.WARNING


# ===== Prometheus YAML =====


def test_rule_to_prometheus_yaml():
    """rule_to_prometheus_yaml: 输出标准 Prometheus 格式."""
    rule = AlertRuleSpec(
        name="TestRule",
        expr='up == 0',
        duration="5m",
        severity=AlertSeverity.WARNING,
        summary="Test",
    )
    yaml = rule_to_prometheus_yaml(rule)
    assert "alert: TestRule" in yaml
    assert "expr: |" in yaml
    assert "for: 5m" in yaml
    assert "severity: warning" in yaml


def test_all_rules_to_yaml_groups():
    """all_rules_to_yaml: 按 group 分组."""
    yaml = all_rules_to_yaml(DEFAULT_ALERT_RULES)
    assert "- name: availability" in yaml
    assert "- name: performance" in yaml
    assert "- name: security" in yaml
    assert "AlertBackendHighErrorRate" in yaml or "BackendHighErrorRate" in yaml
    assert "AuditChainBroken" in yaml


# ===== Alertmanager config =====


def test_alertmanager_config_yaml():
    """alertmanager_config_yaml: 输出 receivers + routes."""
    yaml = alertmanager_config_yaml(DEFAULT_ALERT_ROUTES)
    assert "receivers:" in yaml
    assert "route:" in yaml
    assert "ops-critical" in yaml
    assert "severity = \"critical\"" in yaml


# ===== 集成 / 冒脚 =====


@pytest.mark.asyncio
async def test_alert_rules_module_imports():
    """验证 alert_rules 模块可被导入 (Phase 5 B27 冒脚)."""
    from hscredit_studio.services import alert_rules

    assert hasattr(alert_rules, "DEFAULT_ALERT_RULES")
    assert hasattr(alert_rules, "evaluate_alert")
    assert len(alert_rules.DEFAULT_ALERT_RULES) >= 8
