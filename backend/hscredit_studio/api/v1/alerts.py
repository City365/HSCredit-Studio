"""告警 API — Phase 5 B27.

依据 docs/ROADMAP.md Phase 5 B27:

| 端点 | 方法 | 用途 |
|---|---|---|
| /alerts/rules | GET | 列出告警规则 |
| /alerts/rules | POST | 新增规则 |
| /alerts/prometheus.yaml | GET | 导出 Prometheus rules.yaml |
| /alerts/alertmanager.yaml | GET | 导出 Alertmanager config |
| /alerts/evaluate | POST | 评估单条告警 (路由/抑制/静默) |
| /alerts/instances | GET | 活跃告警实例列表 |
| /alerts/instances | POST | Alertmanager webhook 入站 |
| /alerts/silences | GET | 静默规则列表 |
| /alerts/silences | POST | 新增静默规则 |
| /alerts/history | GET | 发送历史 |
"""
from __future__ import annotations

from datetime import UTC
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Query
from sqlalchemy import select

from hscredit_studio.api.deps import CurrentUserDep, SessionDep
from hscredit_studio.models import AlertHistory, AlertInstance, AlertRule, AlertSilence
from hscredit_studio.schemas.alert import (
    AlertEvaluateRequest,
    AlertEvaluateResponse,
    AlertHistoryItem,
    AlertInstanceIngestRequest,
    AlertInstanceResponse,
    AlertmanagerConfigResponse,
    AlertRuleCreate,
    AlertRuleResponse,
    AlertSilenceCreate,
    AlertSilenceResponse,
    PrometheusRulesResponse,
)
from hscredit_studio.services.alert_rules import (
    DEFAULT_ALERT_ROUTES,
    DEFAULT_ALERT_RULES,
    SilenceRule,
    alertmanager_config_yaml,
    all_rules_to_yaml,
    compute_fingerprint,
    evaluate_alert,
)

router = APIRouter(tags=["告警"])


# ===== 规则 =====


@router.get(
    "/rules",
    summary="列出告警规则",
    response_model=list[AlertRuleResponse],
)
async def list_alert_rules(
    session: SessionDep,
    _: CurrentUserDep,
) -> list[AlertRuleResponse]:
    """列出平台 + 用户自定义告警规则."""
    rows = (
        await session.execute(
            select(AlertRule)
            .where(AlertRule.enabled.is_(True))
            .order_by(AlertRule.group, AlertRule.name)
        )
    ).scalars().all()
    return [
        AlertRuleResponse(
            rule_id=str(r.rule_id),
            name=r.name,
            group=r.group,
            promql=r.promql,
            for_duration=r.for_duration,
            severity=r.severity,
            summary=r.summary,
            description=r.description,
            enabled=r.enabled,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/rules", summary="新增告警规则")
async def create_alert_rule(
    session: SessionDep,
    _: CurrentUserDep,
    body: AlertRuleCreate = Body(...),
) -> AlertRuleResponse:
    """Phase 5 B27 — 新增告警规则."""
    rule = AlertRule(
        name=body.name,
        group=body.group,
        promql=body.promql,
        for_duration=body.for_duration,
        severity=body.severity,
        summary=body.summary,
        description=body.description,
        enabled=body.enabled,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return AlertRuleResponse(
        rule_id=str(rule.rule_id),
        name=rule.name,
        group=rule.group,
        promql=rule.promql,
        for_duration=rule.for_duration,
        severity=rule.severity,
        summary=rule.summary,
        description=rule.description,
        enabled=rule.enabled,
        created_at=rule.created_at,
    )


@router.get(
    "/prometheus.yaml",
    summary="导出 Prometheus rules.yaml",
    response_model=PrometheusRulesResponse,
)
async def export_prometheus_yaml(_: CurrentUserDep) -> PrometheusRulesResponse:
    """Phase 5 B27 — 输出 Prometheus rules.yaml (可直接挂载到 prometheus.yml)."""
    yaml = all_rules_to_yaml(DEFAULT_ALERT_RULES)
    return PrometheusRulesResponse(yaml_content=yaml, rule_count=len(DEFAULT_ALERT_RULES))


@router.get(
    "/alertmanager.yaml",
    summary="导出 Alertmanager config",
    response_model=AlertmanagerConfigResponse,
)
async def export_alertmanager_config(_: CurrentUserDep) -> AlertmanagerConfigResponse:
    """Phase 5 B27 — 输出 Alertmanager receivers + routes config."""
    yaml = alertmanager_config_yaml(DEFAULT_ALERT_ROUTES)
    return AlertmanagerConfigResponse(yaml_content=yaml, route_count=len(DEFAULT_ALERT_ROUTES))


# ===== 评估 =====


@router.post(
    "/evaluate",
    summary="评估告警 (Phase 5 B27 验收)",
    response_model=AlertEvaluateResponse,
)
async def evaluate_alert_endpoint(
    session: SessionDep,
    _: CurrentUserDep,
    body: AlertEvaluateRequest = Body(...),
) -> AlertEvaluateResponse:
    """评估单条告警: 路由 + 抑制 + 静默."""
    silences: list[SilenceRule] = []
    if body.silence_ids:
        rows = (
            await session.execute(
                select(AlertSilence).where(
                    AlertSilence.silence_id.in_([UUID(s) for s in body.silence_ids]),
                    AlertSilence.active.is_(True),
                )
            )
        ).scalars().all()
        for s in rows:
            silences.append(
                SilenceRule(
                    silence_id=str(s.silence_id),
                    matchers=s.matchers or {},
                    starts_at=s.starts_at,
                    ends_at=s.ends_at,
                    created_by=s.created_by,
                    comment=s.comment or "",
                )
            )

    ev = evaluate_alert(body.labels, silences=silences)
    return AlertEvaluateResponse(
        fingerprint=ev.alert_fingerprint,
        severity=ev.severity.value,
        channels=[c.value for c in ev.channels],
        receiver=ev.receiver,
        should_send=ev.should_send,
        should_inhibit=ev.should_inhibit,
        is_silenced=ev.is_silenced,
        inhibit_reason=ev.inhibit_reason,
        silence_reason=ev.silence_reason,
    )


# ===== 实例 =====


@router.get(
    "/instances",
    summary="活跃告警实例",
    response_model=list[AlertInstanceResponse],
)
async def list_alert_instances(
    session: SessionDep,
    _: CurrentUserDep,
    state: str | None = Query(default="firing", pattern="^(firing|resolved)$"),
) -> list[AlertInstanceResponse]:
    """列出告警实例."""
    stmt = select(AlertInstance)
    if state:
        stmt = stmt.where(AlertInstance.state == state)
    stmt = stmt.order_by(AlertInstance.starts_at.desc()).limit(200)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        AlertInstanceResponse(
            instance_id=str(r.instance_id),
            fingerprint=r.fingerprint,
            alert_name=r.alert_name,
            severity=r.severity,
            state=r.state,
            labels=r.labels,
            annotations=r.annotations,
            value=r.value,
            starts_at=r.starts_at,
            ends_at=r.ends_at,
        )
        for r in rows
    ]


@router.post("/instances", summary="Alertmanager webhook 入站")
async def ingest_alert_instance(
    session: SessionDep,
    _: CurrentUserDep,
    body: AlertInstanceIngestRequest = Body(...),
) -> AlertInstanceResponse:
    """Phase 5 B27 — Alertmanager webhook 入库 (去重 by fingerprint)."""
    from datetime import datetime

    fp = body.fingerprint or compute_fingerprint(
        {"alertname": body.alert_name, **body.labels} if body.labels else {"alertname": body.alert_name}
    )
    # PK 是 UUID, 改用 fingerprint 列查重
    existing_row = (
        await session.execute(
            select(AlertInstance).where(AlertInstance.fingerprint == fp)
        )
    ).scalars().first()
    if existing_row is not None:
        existing_row.state = body.state
        if body.state == "resolved":
            existing_row.ends_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(existing_row)
        return AlertInstanceResponse(
            instance_id=str(existing_row.instance_id),
            fingerprint=existing_row.fingerprint,
            alert_name=existing_row.alert_name,
            severity=existing_row.severity,
            state=existing_row.state,
            labels=existing_row.labels,
            annotations=existing_row.annotations,
            value=existing_row.value,
            starts_at=existing_row.starts_at,
            ends_at=existing_row.ends_at,
        )

    instance = AlertInstance(
        fingerprint=fp,
        alert_name=body.alert_name,
        severity=body.severity,
        state=body.state,
        labels=body.labels,
        annotations=body.annotations,
        value=body.value,
        starts_at=body.starts_at or datetime.now(UTC),
    )
    session.add(instance)
    await session.commit()
    await session.refresh(instance)
    return AlertInstanceResponse(
        instance_id=str(instance.instance_id),
        fingerprint=instance.fingerprint,
        alert_name=instance.alert_name,
        severity=instance.severity,
        state=instance.state,
        labels=instance.labels,
        annotations=instance.annotations,
        value=instance.value,
        starts_at=instance.starts_at,
        ends_at=instance.ends_at,
    )


# ===== 静默 =====


@router.get(
    "/silences",
    summary="静默规则列表",
    response_model=list[AlertSilenceResponse],
)
async def list_silences(
    session: SessionDep,
    _: CurrentUserDep,
) -> list[AlertSilenceResponse]:
    """列出静默规则 (含已过期)."""
    rows = (
        await session.execute(
            select(AlertSilence).order_by(AlertSilence.starts_at.desc()).limit(200)
        )
    ).scalars().all()
    return [
        AlertSilenceResponse(
            silence_id=str(r.silence_id),
            matchers=r.matchers,
            starts_at=r.starts_at,
            ends_at=r.ends_at,
            created_by=r.created_by,
            comment=r.comment,
            active=r.active,
        )
        for r in rows
    ]


@router.post("/silences", summary="新增静默规则")
async def create_silence(
    session: SessionDep,
    _: CurrentUserDep,
    body: AlertSilenceCreate = Body(...),
) -> AlertSilenceResponse:
    """Phase 5 B27 — 新增告警静默规则 (时间窗口 + matcher)."""
    silence = AlertSilence(
        matchers=body.matchers,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        created_by="ops",
        comment=body.comment,
        active=True,
    )
    session.add(silence)
    await session.commit()
    await session.refresh(silence)
    return AlertSilenceResponse(
        silence_id=str(silence.silence_id),
        matchers=silence.matchers,
        starts_at=silence.starts_at,
        ends_at=silence.ends_at,
        created_by=silence.created_by,
        comment=silence.comment,
        active=silence.active,
    )


# ===== 历史 =====


@router.get(
    "/history",
    summary="告警发送历史",
    response_model=list[AlertHistoryItem],
)
async def alert_history(
    session: SessionDep,
    _: CurrentUserDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AlertHistoryItem]:
    """Phase 5 B27 — 告警发送历史 (审计追溯)."""
    rows = (
        await session.execute(
            select(AlertHistory).order_by(AlertHistory.sent_at.desc()).limit(limit)
        )
    ).scalars().all()
    return [
        AlertHistoryItem(
            history_id=str(r.history_id),
            alert_name=r.alert_name,
            severity=r.severity,
            channels=r.channels,
            receiver=r.receiver,
            sent_at=r.sent_at,
            suppressed_reason=r.suppressed_reason,
        )
        for r in rows
    ]


@router.get("/severities", summary="告警严重级别")
async def list_severities(_: CurrentUserDep) -> dict[str, Any]:
    """4 级严重级别 + 通道映射 (供前端展示)."""
    return {
        "severities": [
            {"level": "info", "channels": ["slack"]},
            {"level": "warning", "channels": ["email", "slack"]},
            {"level": "critical", "channels": ["email", "slack", "wecom"]},
            {"level": "page", "channels": ["phone", "sms", "wecom"]},
        ]
    }


__all__ = ["router"]
