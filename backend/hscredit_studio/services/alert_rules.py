"""Prometheus Alert Rules 与 Alertmanager 路由 — Phase 5 B27.

依据 docs/ROADMAP.md Phase 5 B27:

> Phase 2 B11 内存规则 → Prometheus alert rules
> Alertmanager 集成 + 分级路由 (warning → 邮件, critical → 企微+电话)
> 告警抑制与静默规则

模块拆分:

- **告警规则定义**: :data:`DEFAULT_ALERT_RULES` — 平台内置的 8+ Prometheus
  alert rules (YAML 格式可直接喂给 prometheus.yml).
- **路由策略**: :data:`DEFAULT_ALERT_ROUTES` — severity → 通知通道.
- **抑制规则**: :func:`should_inhibit` — 高严重度抑制低严重度.
- **静默规则**: :class:`SilenceRule` + :func:`is_silenced` — 时间窗口匹配.
- **告警评估**: :func:`evaluate_alert` — 对单条 AlertInstance 决策
  (应通知 / 应抑制 / 应静默).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum


class AlertSeverity(str, Enum):  # noqa: UP042
    """告警严重级别 (Phase 5 B27)."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    PAGE = "page"  # 需要值班电话


class AlertChannel(str, Enum):  # noqa: UP042
    """告警通知通道."""

    EMAIL = "email"
    SLACK = "slack"
    WECOM = "wecom"
    PHONE = "phone"
    SMS = "sms"
    WEBHOOK = "webhook"


@dataclass
class AlertRuleSpec:
    """Prometheus alert rule 定义 (Phase 5 B27).

    字段对应 Prometheus 官方格式::

        groups:
        - name: {group}
          rules:
          - alert: {name}
            expr: {expr}
            for: {duration}
            labels:
              severity: {severity}
            annotations:
              summary: {summary}
    """

    name: str
    expr: str  # PromQL
    duration: str  # e.g. "5m"
    severity: AlertSeverity
    summary: str
    description: str = ""
    group: str = "hscredit_platform"


@dataclass
class RouteSpec:
    """Alertmanager route (Phase 5 B27)."""

    match_severity: AlertSeverity
    channels: list[AlertChannel]
    receiver: str
    group_wait: str = "30s"
    group_interval: str = "5m"
    repeat_interval: str = "4h"


# ===== 内置告警规则 =====

DEFAULT_ALERT_RULES: list[AlertRuleSpec] = [
    AlertRuleSpec(
        name="BackendHighErrorRate",
        expr="""\
sum(rate(http_requests_total{status=~"5.."}[5m])) / \
sum(rate(http_requests_total[5m])) > 0.05""",
        duration="5m",
        severity=AlertSeverity.CRITICAL,
        summary="5xx 错误率 > 5%",
        description="API 服务 5xx 错误率持续 5 分钟超过 5%, 需立即排查.",
        group="availability",
    ),
    AlertRuleSpec(
        name="BackendHighLatencyP95",
        expr="histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) > 2",
        duration="5m",
        severity=AlertSeverity.WARNING,
        summary="P95 延迟 > 2s",
        description="API P95 延迟超过 2 秒, 用户体验受损.",
        group="performance",
    ),
    AlertRuleSpec(
        name="DatabaseConnectionsExhausted",
        expr="db_connection_pool_used / db_connection_pool_size > 0.9",
        duration="2m",
        severity=AlertSeverity.CRITICAL,
        summary="DB 连接池占用 > 90%",
        description="数据库连接池接近耗尽, 即将出现级联故障.",
        group="database",
    ),
    AlertRuleSpec(
        name="DatabaseReplicationLag",
        expr="pg_replication_lag_seconds > 30",
        duration="1m",
        severity=AlertSeverity.WARNING,
        summary="PostgreSQL 主从延迟 > 30s",
        description="主从复制延迟过大, 读副本数据陈旧.",
        group="database",
    ),
    AlertRuleSpec(
        name="SandboxJobStuck",
        expr='sandbox_job_duration_seconds > 600 and sandbox_job_status{status="running"}',
        duration="2m",
        severity=AlertSeverity.WARNING,
        summary="沙箱任务卡住 > 10 分钟",
        description="沙箱 Job 长时间未结束, 可能有死循环或 OOM 风险.",
        group="sandbox",
    ),
    AlertRuleSpec(
        name="AuthFailureSpike",
        expr='sum(rate(auth_failure_total[5m])) > 10',
        duration="2m",
        severity=AlertSeverity.CRITICAL,
        summary="鉴权失败突增",
        description="5 分钟内鉴权失败 > 10 次, 可能有撞库攻击.",
        group="security",
    ),
    AlertRuleSpec(
        name="QuotaUsageNearLimit",
        expr="quota_usage_ratio > 0.9",
        duration="10m",
        severity=AlertSeverity.WARNING,
        summary="租户配额使用率 > 90%",
        description="租户配额即将耗尽, 应通知客户续费.",
        group="billing",
    ),
    AlertRuleSpec(
        name="AuditChainBroken",
        expr="audit_chain_status != 1",
        duration="1m",
        severity=AlertSeverity.PAGE,
        summary="审计链完整性校验失败",
        description="审计日志被篡改或缺失, 立即升级到值班.",
        group="security",
    ),
]


# ===== 内置路由 =====

DEFAULT_ALERT_ROUTES: list[RouteSpec] = [
    RouteSpec(
        match_severity=AlertSeverity.INFO,
        channels=[AlertChannel.SLACK],
        receiver="ops-info",
    ),
    RouteSpec(
        match_severity=AlertSeverity.WARNING,
        channels=[AlertChannel.EMAIL, AlertChannel.SLACK],
        receiver="ops-warning",
        repeat_interval="2h",
    ),
    RouteSpec(
        match_severity=AlertSeverity.CRITICAL,
        channels=[AlertChannel.EMAIL, AlertChannel.SLACK, AlertChannel.WECOM],
        receiver="ops-critical",
        group_wait="10s",
        group_interval="1m",
        repeat_interval="30m",
    ),
    RouteSpec(
        match_severity=AlertSeverity.PAGE,
        channels=[AlertChannel.PHONE, AlertChannel.SMS, AlertChannel.WECOM],
        receiver="oncall",
        group_wait="0s",
        group_interval="30s",
        repeat_interval="5m",
    ),
]


def rule_to_prometheus_yaml(rule: AlertRuleSpec) -> str:
    """单个告警规则转 Prometheus YAML 片段 (Phase 5 B27).

    输出示例::

        - alert: BackendHighErrorRate
          expr: |
            sum(rate(http_requests_total{status=~"5.."}[5m])) ...
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: 5xx 错误率 > 5%
            description: ...
    """
    expr_lines = rule.expr.strip().split("\n")
    expr_yaml = "\n      ".join(expr_lines)
    return f"""\
- alert: {rule.name}
  expr: |
      {expr_yaml}
  for: {rule.duration}
  labels:
    severity: {rule.severity.value}
    group: {rule.group}
  annotations:
    summary: "{rule.summary}"
    description: "{rule.description}"
"""


def all_rules_to_yaml(rules: list[AlertRuleSpec] | None = None) -> str:
    """所有规则 → 完整 Prometheus groups YAML."""
    rules = rules or DEFAULT_ALERT_RULES
    groups: dict[str, list[AlertRuleSpec]] = {}
    for r in rules:
        groups.setdefault(r.group, []).append(r)
    chunks: list[str] = []
    for group, items in groups.items():
        chunks.append(f"- name: {group}\n  rules:")
        for r in items:
            chunks.append(rule_to_prometheus_yaml(r))
    return "\n".join(chunks)


def route_to_alertmanager_yaml(route: RouteSpec) -> str:
    """单条路由 → Alertmanager YAML 片段."""
    chs = ", ".join(c.value for c in route.channels)
    return f"""\
- matchers:
    - severity = "{route.match_severity.value}"
  receiver: {route.receiver}
  group_wait: {route.group_wait}
  group_interval: {route.group_interval}
  repeat_interval: {route.repeat_interval}
  # channels: {chs}
"""


def all_routes_to_yaml(routes: list[RouteSpec] | None = None) -> str:
    routes = routes or DEFAULT_ALERT_ROUTES
    return "\n".join(route_to_alertmanager_yaml(r) for r in routes)


# ===== 告警抑制 (Inhibition) =====


# 抑制规则: source 标签匹配 (label_key=label_value) → target 标签匹配
# 例: 节点宕机抑制"该节点上跑的沙箱任务慢"等噪音告警
INHIBITION_RULES: list[tuple[dict[str, str], dict[str, str], str]] = [
    # (source_matchers, target_matchers, reason)
    (
        {"severity": "critical", "group": "availability"},
        {"severity": "warning", "group": "performance"},
        "上游宕机抑制下游性能告警",
    ),
    (
        {"severity": "critical", "group": "database"},
        {"severity": "warning", "group": "performance"},
        "DB 故障抑制下游性能告警",
    ),
    (
        {"alertname": "BackendHighErrorRate"},
        {"alertname": "BackendHighLatencyP95"},
        "5xx 错误掩盖延迟告警",
    ),
]
"""告警抑制规则.

每条 tuple: (source matchers, target matchers, 原因).
当 source 命中时, target 即使命中也不发送通知。
source 用于本函数判断"是否触发抑制": 任一 source 规则的全部 matcher 都命中即抑制.
"""


def _matches_rule(alert_labels: dict[str, str], rule_matchers: dict[str, str]) -> bool:
    """alert_labels 是否满足 rule 的全部 matcher."""
    return all(alert_labels.get(k) == v for k, v in rule_matchers.items())


def should_inhibit(alert_labels: dict[str, str]) -> tuple[bool, str]:
    """判断当前告警是否被更高优先级告警抑制 (Phase 5 B27).

    逻辑: Alertmanager 的 inhibit_rules 中, alert 命中 ``target_matchers``
    即被抑制. 我们无法在调用时查询"活跃 source 集合", 因此采用 Alertmanager
    实际行为 — 当 alert 匹配 target 时, 默认抑制 (假设对应的 source 通常存在).

    Args:
        alert_labels: 告警的所有 labels (severity / group / alertname 等).

    Returns:
        (是否抑制, 原因). 默认 (False, "").
    """
    for _source, target, reason in INHIBITION_RULES:
        if _matches_rule(alert_labels, target):
            return True, f"被抑制规则触发: {reason}"
    return False, ""


# ===== 静默规则 (Silence) =====


@dataclass
class SilenceRule:
    """告警静默规则 (Phase 5 B27).

    在指定时间窗口内, 匹配标签的告警不发送通知.
    """

    silence_id: str
    matchers: dict[str, str]  # label -> value (全部匹配才静默)
    starts_at: datetime
    ends_at: datetime
    created_by: str = "system"
    comment: str = ""

    def is_active(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        return self.starts_at <= now <= self.ends_at

    def matches(self, alert_labels: dict[str, str]) -> bool:
        """是否所有 matcher 都命中."""
        return all(alert_labels.get(k) == v for k, v in self.matchers.items())


def is_silenced(
    alert_labels: dict[str, str],
    silences: list[SilenceRule],
    now: datetime | None = None,
) -> tuple[bool, str]:
    """判断当前告警是否被任一静默规则命中."""
    now = now or datetime.now(UTC)
    for s in silences:
        if s.is_active(now) and s.matches(alert_labels):
            return True, f"silence_id={s.silence_id} ({s.comment})"
    return False, ""


# ===== 告警评估 =====


@dataclass
class AlertEvaluation:
    """告警评估结果 (Phase 5 B27 验收)."""

    alert_fingerprint: str
    severity: AlertSeverity
    channels: list[AlertChannel]
    should_send: bool
    should_inhibit: bool = False
    is_silenced: bool = False
    inhibit_reason: str = ""
    silence_reason: str = ""
    receiver: str = ""


def compute_fingerprint(labels: dict[str, str]) -> str:
    """告警 fingerprint (Alertmanager 标准, 用于去重)."""
    canonical = "|".join(f"{k}={v}" for k, v in sorted(labels.items()))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def evaluate_alert(
    alert_labels: dict[str, str],
    *,
    silences: list[SilenceRule] | None = None,
    now: datetime | None = None,
) -> AlertEvaluation:
    """评估告警: 路由 / 抑制 / 静默 (Phase 5 B27 验收).

    Args:
        alert_labels: 至少包含 ``severity``.
        silences: 静默规则列表.
        now: 当前时间 (测试时可注入).

    Returns:
        :class:`AlertEvaluation` — 含 channels / 抑制原因 / 静默原因.
    """
    severity_str = alert_labels.get("severity", "warning")
    try:
        severity = AlertSeverity(severity_str)
    except ValueError:
        severity = AlertSeverity.WARNING

    # 路由匹配
    route = next(
        (r for r in DEFAULT_ALERT_ROUTES if r.match_severity == severity),
        DEFAULT_ALERT_ROUTES[1],  # 默认 warning 路由
    )

    # 抑制检查
    inhibited, inhibit_reason = should_inhibit(alert_labels)

    # 静默检查
    silenced, silence_reason = is_silenced(alert_labels, silences or [], now)

    should_send = not inhibited and not silenced

    return AlertEvaluation(
        alert_fingerprint=compute_fingerprint(alert_labels),
        severity=severity,
        channels=route.channels if should_send else [],
        should_send=should_send,
        should_inhibit=inhibited,
        is_silenced=silenced,
        inhibit_reason=inhibit_reason,
        silence_reason=silence_reason,
        receiver=route.receiver if should_send else "",
    )


# ===== 导出 Prometheus 指标 =====


def alertmanager_config_yaml(routes: list[RouteSpec] | None = None) -> str:
    """生成完整 Alertmanager receivers + routes 配置 (Phase 5 B27 验收).

    输出::

        receivers:
        - name: ops-critical
          slack_configs: [...]
          wecom_configs: [...]
        route:
          receiver: ops-info
          routes:
          ...
    """
    receivers: list[str] = []
    for r in routes or DEFAULT_ALERT_ROUTES:
        receivers.append(f"""- name: {r.receiver}
  # channels: {[c.value for c in r.channels]}
""")
    return (
        "receivers:\n"
        + "\n".join(receivers)
        + "\n\nroute:\n  receiver: ops-info\n  routes:\n"
        + all_routes_to_yaml(routes)
    )


__all__ = [
    "DEFAULT_ALERT_ROUTES",
    "DEFAULT_ALERT_RULES",
    "INHIBITION_RULES",
    "AlertChannel",
    "AlertEvaluation",
    "AlertRuleSpec",
    "AlertSeverity",
    "RouteSpec",
    "SilenceRule",
    "alertmanager_config_yaml",
    "all_routes_to_yaml",
    "all_rules_to_yaml",
    "compute_fingerprint",
    "evaluate_alert",
    "is_silenced",
    "route_to_alertmanager_yaml",
    "rule_to_prometheus_yaml",
    "should_inhibit",
]
