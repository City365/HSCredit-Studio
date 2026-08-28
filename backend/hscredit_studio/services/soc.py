"""SOC 安全运营中心 — Phase 5 B25.

依据 docs/ROADMAP.md Phase 5 B25:

> 对接 SIEM (Splunk/QRadar) 或自建安全运营
> 渗透测试报告闭环

模块化拆分:

- **审计日志导出 (CEF / Syslog)**: :func:`export_events_cef`,
  :func:`export_events_syslog` — 对接 Splunk / QRadar
- **安全指标聚合**: :func:`aggregate_security_metrics` — SOC 仪表板
- **渗透测试发现**: :func:`list_vulnerabilities`,
  :func:`update_vulnerability_status` — 闭环跟踪
- **审计链完整性**: :func:`verify_recent_audit_chain` — 定时任务调用
"""
from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.logging import get_logger
from hscredit_studio.models import AuditEvent, Vulnerability
from hscredit_studio.services.security_hardening import (
    verify_audit_chain,
)

_log = get_logger(__name__)


# ===== SIEM 导出 (CEF 格式) =====

# CEF (Common Event Format) 格式示例:
# CEF:0|Device Vendor|Device Product|Device Version|Signature ID|Name|Severity|Extension
# 这里自定义 Vendor / Product 为 HSCredit Studio.

_SIEM_VENDOR = "HSCredit"
_SIEM_PRODUCT = "HSCredit-Studio"
_SIEM_VERSION = "0.1.0"

# action → CEF signature_id 映射 (Splunk 可基于此聚合)
_ACTION_TO_SIGNATURE: dict[str, str] = {
    "login": "1001",
    "login_failed": "1002",
    "auth_failure": "1003",
    "logout": "1004",
    "permission_change": "2001",
    "config_change": "2002",
    "data_access": "3001",
    "data_export": "3002",
    "image_export": "3003",
    "model_export": "3004",
    "workflow_create": "4001",
    "workflow_update": "4002",
    "workflow_delete": "4003",
    "workflow_run_submit": "4004",
}

# action → severity (1=low ... 10=critical)
_ACTION_SEVERITY: dict[str, int] = {
    "login": 1,
    "logout": 1,
    "login_failed": 3,
    "auth_failure": 5,
    "permission_change": 6,
    "config_change": 5,
    "data_access": 2,
    "data_export": 6,
    "image_export": 6,
    "model_export": 7,
    "workflow_create": 2,
    "workflow_update": 2,
    "workflow_delete": 5,
    "workflow_run_submit": 2,
    "workflow_run_cancel": 3,
    "apikey_create": 5,
    "apikey_revoke": 4,
    "user_create": 4,
    "user_delete": 6,
}


def export_events_cef(events: Iterable[dict[str, Any]]) -> str:
    """审计事件导出 CEF 格式 (Phase 5 B25 SIEM 集成).

    CEF (Common Event Format) 是 ArcSight 提出的行业标准格式,
    Splunk / QRadar / Elastic 均支持.

    Args:
        events: 审计事件列表 (新到旧或旧到新均可).

    Returns:
        多行 CEF 字符串.
    """
    lines: list[str] = []
    for ev in events:
        sig_id = _ACTION_TO_SIGNATURE.get(ev.get("action", ""), "9999")
        severity = _ACTION_SEVERITY.get(ev.get("action", ""), 5)
        name = ev.get("action", "unknown")
        ts = ev.get("occurred_at", "")
        if isinstance(ts, datetime):
            ts = ts.isoformat()
        # CEF Header
        header = (
            f"CEF:0|{_SIEM_VENDOR}|{_SIEM_PRODUCT}|{_SIEM_VERSION}|"
            f"{sig_id}|{name}|{severity}|"
        )
        # Extension
        ext_parts = [
            f"rt={_format_cef_timestamp(ts)}",
            f"dvchost={_SIEM_PRODUCT}",
            f"cs1={ev.get('tenant_id', '')} cs1Label=tenant_id",
            f"cs2={ev.get('user_id', '')} cs2Label=user_id",
            f"cs3={ev.get('resource_type', '')} cs3Label=resource_type",
            f"cs4={ev.get('resource_id', '')} cs4Label=resource_id",
            f"src={ev.get('ip_address', '')}",
            f"requestClientApplication={ev.get('user_agent', '')[:200]}",
            f"act={ev.get('action', '')}",
        ]
        # details 字段以 msg= 包含
        details = ev.get("details") or {}
        if details:
            ext_parts.append(f"msg={_cef_escape(str(details))[:1024]}")
        lines.append(header + " ".join(ext_parts))
    return "\n".join(lines)


def export_events_syslog(events: Iterable[dict[str, Any]], facility: int = 1) -> str:
    """审计事件导出 Syslog (RFC 5424) 格式 (Phase 5 B25 SIEM 集成).

    Args:
        events: 审计事件列表.
        facility: syslog facility (1=user-level, 默认).

    Returns:
        多行 RFC 5424 syslog 字符串.
    """
    lines: list[str] = []
    for ev in events:
        ts = ev.get("occurred_at", datetime.utcnow())
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except ValueError:
                ts = datetime.utcnow()
        ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        # Priority = facility * 8 + severity
        severity = _ACTION_SEVERITY.get(ev.get("action", ""), 5)
        priority = facility * 8 + min(severity, 7)
        msg = (
            f"HSCredit audit: action={ev.get('action', '')} "
            f"tenant={ev.get('tenant_id', '')} user={ev.get('user_id', '')} "
            f"ip={ev.get('ip_address', '')} details={ev.get('details', '')}"
        )
        lines.append(f"<{priority}>1 {ts_str} hscredit-studio hscredit-studio - - - {msg}")
    return "\n".join(lines)


def _format_cef_timestamp(ts: Any) -> str:
    """CEF 时间戳格式: MMM dd yyyy HH:mm:ss."""
    if isinstance(ts, datetime):
        return ts.strftime("%b %d %Y %H:%M:%S")
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts).strftime("%b %d %Y %H:%M:%S")
        except ValueError:
            return ts
    return ""


def _cef_escape(value: str) -> str:
    """CEF extension 值转义 (避免 | / \n 破坏解析)."""
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "\\n")


# ===== 安全指标聚合 =====


@dataclass
class SecurityMetrics:
    """安全运营指标 (Phase 5 B25 SOC 仪表板)."""

    total_events: int
    failed_logins: int
    auth_failures: int
    sensitive_data_access: int
    data_exports: int
    permission_changes: int
    config_changes: int
    top_actions: list[tuple[str, int]]
    top_ips: list[tuple[str, int]]
    window_days: int
    generated_at: str


async def aggregate_security_metrics(
    session: AsyncSession,
    *,
    tenant_id: UUID | None = None,
    window_days: int = 7,
) -> SecurityMetrics:
    """聚合安全指标 (Phase 5 B25 SOC 仪表板).

    Args:
        session: AsyncSession.
        tenant_id: 限定单租户 (None = 全平台).
        window_days: 时间窗口 (默认 7 天).

    Returns:
        :class:`SecurityMetrics`.
    """
    since = datetime.utcnow() - timedelta(days=window_days)
    conditions = [AuditEvent.occurred_at >= since]
    if tenant_id is not None:
        conditions.append(AuditEvent.tenant_id == tenant_id)
    where_clause = and_(*conditions)

    total = int(
        await session.scalar(select(func.count(AuditEvent.event_id)).where(where_clause)) or 0
    )

    failed_logins = int(
        await session.scalar(
            select(func.count(AuditEvent.event_id)).where(
                and_(where_clause, AuditEvent.action == "login_failed")
            )
        )
        or 0
    )
    auth_failures = int(
        await session.scalar(
            select(func.count(AuditEvent.event_id)).where(
                and_(where_clause, AuditEvent.action == "auth_failure")
            )
        )
        or 0
    )
    sensitive_data = int(
        await session.scalar(
            select(func.count(AuditEvent.event_id)).where(
                and_(where_clause, AuditEvent.action == "data_access")
            )
        )
        or 0
    )
    data_exports = int(
        await session.scalar(
            select(func.count(AuditEvent.event_id)).where(
                and_(where_clause, AuditEvent.action == "data_export")
            )
        )
        or 0
    )
    perm_changes = int(
        await session.scalar(
            select(func.count(AuditEvent.event_id)).where(
                and_(where_clause, AuditEvent.action == "permission_change")
            )
        )
        or 0
    )
    config_changes = int(
        await session.scalar(
            select(func.count(AuditEvent.event_id)).where(
                and_(where_clause, AuditEvent.action == "config_change")
            )
        )
        or 0
    )

    # Top actions
    top_action_rows = (
        await session.execute(
            select(AuditEvent.action, func.count(AuditEvent.event_id).label("cnt"))
            .where(where_clause)
            .group_by(AuditEvent.action)
            .order_by(func.count(AuditEvent.event_id).desc())
            .limit(10)
        )
    ).all()
    top_actions = [(str(r.action), int(r.cnt)) for r in top_action_rows]

    # Top IPs (排除 None)
    top_ip_rows = (
        await session.execute(
            select(AuditEvent.ip_address, func.count(AuditEvent.event_id).label("cnt"))
            .where(where_clause, AuditEvent.ip_address.isnot(None))
            .group_by(AuditEvent.ip_address)
            .order_by(func.count(AuditEvent.event_id).desc())
            .limit(10)
        )
    ).all()
    top_ips = [(str(r.ip_address), int(r.cnt)) for r in top_ip_rows]

    return SecurityMetrics(
        total_events=total,
        failed_logins=failed_logins,
        auth_failures=auth_failures,
        sensitive_data_access=sensitive_data,
        data_exports=data_exports,
        permission_changes=perm_changes,
        config_changes=config_changes,
        top_actions=top_actions,
        top_ips=top_ips,
        window_days=window_days,
        generated_at=datetime.utcnow().isoformat() + "Z",
    )


# ===== 审计链完整性 =====


@dataclass
class ChainCheckResult:
    """审计链完整性检查结果 (Phase 5 B25)."""

    is_valid: bool
    checked_count: int
    failed_event_id: str | None
    error: str | None
    checked_at: str


async def verify_recent_audit_chain(
    session: AsyncSession,
    *,
    tenant_id: UUID | None = None,
    hours: int = 24,
    secret: str = "",
) -> ChainCheckResult:
    """验证最近 N 小时审计链 (Phase 5 B25 验收).

    通常由定时任务 (cron) 调用, 若失败触发 SOC 告警.

    Args:
        session: AsyncSession.
        tenant_id: 限定租户 (None = 全平台).
        hours: 时间窗口 (默认 24h).
        secret: HMAC 密钥 (空 = 跳过链验证, 仅返回事件数).
    """
    since = datetime.utcnow() - timedelta(hours=hours)
    conditions = [AuditEvent.occurred_at >= since]
    if tenant_id is not None:
        conditions.append(AuditEvent.tenant_id == tenant_id)

    rows = (
        await session.execute(
            select(AuditEvent)
            .where(and_(*conditions))
            .order_by(AuditEvent.occurred_at.asc(), AuditEvent.event_id.asc())
        )
    ).scalars().all()

    # 若无 secret, 仅返回统计
    if not secret:
        return ChainCheckResult(
            is_valid=True,
            checked_count=len(rows),
            failed_event_id=None,
            error="未配置 HMAC secret, 跳过链验证",
            checked_at=datetime.utcnow().isoformat() + "Z",
        )

    events_dict: list[dict[str, Any]] = []
    for r in rows:
        events_dict.append(
            {
                "event_id": str(r.event_id),
                "tenant_id": str(r.tenant_id),
                "user_id": str(r.user_id) if r.user_id else None,
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": str(r.resource_id) if r.resource_id else None,
                "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
            }
        )

    result = verify_audit_chain(events_dict, secret)
    return ChainCheckResult(
        is_valid=result.is_valid,
        checked_count=result.checked_count,
        failed_event_id=result.failed_event_id,
        error=result.error,
        checked_at=datetime.utcnow().isoformat() + "Z",
    )


# ===== 渗透测试发现跟踪 =====


async def list_vulnerabilities(
    session: AsyncSession,
    *,
    status: str | None = None,
    severity: str | None = None,
    limit: int = 100,
) -> list[Vulnerability]:
    """列出渗透测试发现项 (Phase 5 B25 渗透测试闭环)."""
    stmt = select(Vulnerability)
    if status:
        stmt = stmt.where(Vulnerability.status == status)
    if severity:
        stmt = stmt.where(Vulnerability.severity == severity)
    stmt = stmt.order_by(Vulnerability.discovered_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def update_vulnerability_status(
    session: AsyncSession,
    *,
    vuln_id: UUID,
    status: str,
    fix_notes: str | None = None,
) -> Vulnerability | None:
    """更新漏洞处置状态 (Phase 5 B25 验收)."""
    v = await session.get(Vulnerability, vuln_id)
    if v is None:
        return None
    v.status = status
    if fix_notes:
        v.fix_notes = fix_notes
    if status == "closed":
        v.closed_at = datetime.utcnow()
    await session.commit()
    await session.refresh(v)
    return v


async def create_vulnerability(
    session: AsyncSession,
    *,
    title: str,
    severity: str,
    description: str,
    remediation: str,
    discovered_at: datetime | None = None,
) -> Vulnerability:
    """登记一个新发现的漏洞."""
    v = Vulnerability(
        title=title,
        severity=severity,
        description=description,
        remediation=remediation,
        status="open",
        discovered_at=discovered_at or datetime.utcnow(),
    )
    session.add(v)
    await session.commit()
    await session.refresh(v)
    return v


# ===== CSV 导出审计 (辅助) =====


def export_events_csv(events: Iterable[dict[str, Any]]) -> bytes:
    """审计事件导出 CSV (供 SOC 离线分析)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "event_id",
            "occurred_at",
            "tenant_id",
            "user_id",
            "action",
            "resource_type",
            "resource_id",
            "ip_address",
            "user_agent",
            "details",
        ]
    )
    for r in events:
        writer.writerow(
            [
                r.get("event_id", ""),
                r.get("occurred_at", ""),
                r.get("tenant_id", ""),
                r.get("user_id", ""),
                r.get("action", ""),
                r.get("resource_type", ""),
                r.get("resource_id", ""),
                r.get("ip_address", ""),
                (r.get("user_agent") or "")[:500],
                str(r.get("details", "")),
            ]
        )
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


__all__ = [
    "ChainCheckResult",
    "SecurityMetrics",
    "aggregate_security_metrics",
    "create_vulnerability",
    "export_events_cef",
    "export_events_csv",
    "export_events_syslog",
    "list_vulnerabilities",
    "update_vulnerability_status",
    "verify_recent_audit_chain",
]
