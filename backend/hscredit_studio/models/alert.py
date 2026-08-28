"""告警持久化模型 — Phase 5 B27.

依据 docs/ROADMAP.md Phase 5 B27:

> Alertmanager 集成 + 分级路由
> 告警抑制与静默规则

表设计:

- ``alert_rules`` — 告警规则定义 (可被 Prometheus reload)
- ``alert_instances`` — 当前活跃告警实例 (Alertmanager webhook 入站)
- ``alert_silences`` — 静默规则 (时间窗口 + matcher)
- ``alert_history`` — 已发送告警历史 (审计 + 追溯)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from hscredit_studio.core.database import Base
from hscredit_studio.models.base import TimestampMixin

ALERT_STATE_VALUES = ("firing", "resolved")
ALERT_SEVERITY_VALUES = ("info", "warning", "critical", "page")
ALERT_CHANNEL_VALUES = ("email", "slack", "wecom", "phone", "sms", "webhook")


class AlertRule(Base, TimestampMixin):
    """告警规则定义 — Phase 5 B27.

    与 Prometheus rule_files 对齐. 字段 ``promql`` 喂给 alert expr,
    ``for_duration`` 决定持续多久才触发.
    """

    __tablename__ = "alert_rules"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        comment="规则名 (e.g. BackendHighErrorRate)",
    )
    group: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'default'"),
        comment="分组 (availability / performance / database / security / billing)",
    )
    promql: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="PromQL 表达式",
    )
    for_duration: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'5m'"),
        comment="持续时间 (e.g. 5m / 1m)",
    )
    severity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=f"严重级别 {ALERT_SEVERITY_VALUES}",
    )
    summary: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        comment="告警摘要",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="详细说明",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        comment="是否启用",
    )

    __table_args__ = (
        Index("ix_alert_rules_group", "group"),
        Index("ix_alert_rules_severity", "severity"),
        Index("ix_alert_rules_enabled", "enabled"),
    )


class AlertInstance(Base, TimestampMixin):
    """活跃告警实例 (Phase 5 B27).

    Alertmanager webhook → 入库. ``fingerprint`` 用于去重.
    """

    __tablename__ = "alert_instances"

    instance_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    fingerprint: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        comment="告警 fingerprint (sha256[16]) 用于去重",
    )
    alert_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="告警规则名",
    )
    severity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=f"严重级别 {ALERT_SEVERITY_VALUES}",
    )
    state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'firing'"),
        comment=f"状态 {ALERT_STATE_VALUES}",
    )
    labels: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="告警 labels (k8s_pod, region, ...)",
    )
    annotations: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="告警 annotations (summary, description)",
    )
    value: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="当前指标值 (字符串化)",
    )
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="触发时间",
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="恢复时间 (firing → resolved 时填)",
    )

    __table_args__ = (
        Index("ix_alert_instances_state", "state"),
        Index("ix_alert_instances_severity", "severity"),
        Index("ix_alert_instances_starts_at", "starts_at"),
    )


class AlertSilence(Base, TimestampMixin):
    """告警静默规则 (Phase 5 B27).

    时间窗口内, 匹配 matchers 的告警不发送通知.
    """

    __tablename__ = "alert_silences"

    silence_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    matchers: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="标签匹配 (label -> value, 全匹配)",
    )
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="开始时间",
    )
    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="结束时间",
    )
    created_by: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'system'"),
        comment="创建人 (ops / dpa / system)",
    )
    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="静默原因",
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        comment="是否启用",
    )

    __table_args__ = (
        Index("ix_alert_silences_active", "starts_at", "ends_at"),
        Index("ix_alert_silences_active_flag", "active"),
    )


class AlertHistory(Base, TimestampMixin):
    """已发送告警历史 — Phase 5 B27.

    用于审计 + 追溯. 每次 evaluate_alert 决定发送时记一行.
    """

    __tablename__ = "alert_history"

    history_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    alert_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="触发的告警规则",
    )
    severity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=f"严重级别 {ALERT_SEVERITY_VALUES}",
    )
    channels: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="已通知通道列表",
    )
    receiver: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Alertmanager receiver",
    )
    labels: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="告警 labels",
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="发送时间",
    )
    suppressed_reason: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        comment="抑制 / 静默原因 (如未发送)",
    )

    __table_args__ = (
        Index("ix_alert_history_sent_at", "sent_at"),
        Index("ix_alert_history_severity", "severity"),
    )


__all__ = [
    "ALERT_CHANNEL_VALUES",
    "ALERT_SEVERITY_VALUES",
    "ALERT_STATE_VALUES",
    "AlertHistory",
    "AlertInstance",
    "AlertRule",
    "AlertSilence",
]
