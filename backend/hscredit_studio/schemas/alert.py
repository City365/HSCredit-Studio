"""告警 Schema — Phase 5 B27."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ===== 规则 =====


class AlertRuleCreate(BaseModel):
    """新增告警规则."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., max_length=128)
    group: str = Field(default="default", max_length=64)
    promql: str
    for_duration: str = Field(default="5m", max_length=16)
    severity: str = Field(..., pattern="^(info|warning|critical|page)$")
    summary: str = Field(..., max_length=256)
    description: str | None = None
    enabled: bool = Field(default=True)


class AlertRuleResponse(BaseModel):
    """告警规则响应."""

    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    name: str
    group: str
    promql: str
    for_duration: str
    severity: str
    summary: str
    description: str | None
    enabled: bool
    created_at: datetime


class PrometheusRulesResponse(BaseModel):
    """Prometheus rules.yaml 输出."""

    model_config = ConfigDict(from_attributes=True)

    yaml_content: str
    rule_count: int


class AlertmanagerConfigResponse(BaseModel):
    """Alertmanager config.yaml 输出."""

    model_config = ConfigDict(from_attributes=True)

    yaml_content: str
    route_count: int


# ===== 实例 =====


class AlertInstanceIngestRequest(BaseModel):
    """Alertmanager webhook 入站 (Phase 5 B27)."""

    model_config = ConfigDict(from_attributes=True)

    fingerprint: str = Field(..., max_length=32)
    alert_name: str = Field(..., max_length=128)
    severity: str = Field(..., pattern="^(info|warning|critical|page)$")
    state: str = Field(default="firing", pattern="^(firing|resolved)$")
    labels: dict[str, str] | None = None
    annotations: dict[str, Any] | None = None
    value: str | None = None
    starts_at: datetime | None = None


class AlertInstanceResponse(BaseModel):
    """活跃告警实例响应."""

    model_config = ConfigDict(from_attributes=True)

    instance_id: str
    fingerprint: str
    alert_name: str
    severity: str
    state: str
    labels: dict[str, Any] | None
    annotations: dict[str, Any] | None
    value: str | None
    starts_at: datetime
    ends_at: datetime | None


# ===== 静默 =====


class AlertSilenceCreate(BaseModel):
    """创建静默规则."""

    model_config = ConfigDict(from_attributes=True)

    matchers: dict[str, str] = Field(..., description="标签匹配 (label -> value)")
    starts_at: datetime
    ends_at: datetime
    comment: str | None = None


class AlertSilenceResponse(BaseModel):
    """静默规则响应."""

    model_config = ConfigDict(from_attributes=True)

    silence_id: str
    matchers: dict[str, str]
    starts_at: datetime
    ends_at: datetime
    created_by: str
    comment: str | None
    active: bool


# ===== 评估 =====


class AlertEvaluateRequest(BaseModel):
    """评估告警 (Phase 5 B27 验收)."""

    model_config = ConfigDict(from_attributes=True)

    labels: dict[str, str] = Field(..., description="告警 labels (含 severity)")
    silence_ids: list[str] | None = None


class AlertEvaluateResponse(BaseModel):
    """告警评估响应."""

    model_config = ConfigDict(from_attributes=True)

    fingerprint: str
    severity: str
    channels: list[str]
    receiver: str
    should_send: bool
    should_inhibit: bool
    is_silenced: bool
    inhibit_reason: str
    silence_reason: str


# ===== 历史 =====


class AlertHistoryItem(BaseModel):
    """告警历史项."""

    model_config = ConfigDict(from_attributes=True)

    history_id: str
    alert_name: str
    severity: str
    channels: list[str] | None
    receiver: str | None
    sent_at: datetime
    suppressed_reason: str | None


__all__ = [
    "AlertEvaluateRequest",
    "AlertEvaluateResponse",
    "AlertHistoryItem",
    "AlertInstanceIngestRequest",
    "AlertInstanceResponse",
    "AlertRuleCreate",
    "AlertRuleResponse",
    "AlertSilenceCreate",
    "AlertSilenceResponse",
    "AlertmanagerConfigResponse",
    "PrometheusRulesResponse",
]
