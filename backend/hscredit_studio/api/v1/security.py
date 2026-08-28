"""安全加固 API — Phase 5 B25.

依据 docs/ROADMAP.md Phase 5 B25:

| 端点 | 方法 | 用途 |
|---|---|---|
| /security/metrics | GET | SOC 仪表板指标 |
| /security/audit-integrity | GET | 审计链完整性检查 |
| /security/export | GET | 审计日志 SIEM 导出 (CEF/syslog/csv) |
| /security/intrusion-check | POST | 入侵检测 (供中间件 / 测试) |
| /security/password-check | POST | 密码复杂度校验 |
| /security/ip-rules | GET/POST | IP 黑白名单管理 |
| /security/ip-rules/{id} | DELETE | 删除 IP 规则 |
| /security/ip-check | POST | 检查 IP 是否允许访问 |
| /security/vulnerabilities | GET/POST | 漏洞列表 / 新增 |
| /security/vulnerabilities/{id} | PATCH | 漏洞状态更新 |
| /security/vulnerabilities/stats | GET | 漏洞统计 (等保关闭率) |
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Query
from sqlalchemy import func, select

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep
from hscredit_studio.core.config import settings
from hscredit_studio.models import (
    AuditEvent,
    IpAccessRule,
    Vulnerability,
)
from hscredit_studio.schemas.security import (
    IntrusionCheckRequest,
    IntrusionCheckResponse,
    IpAccessRuleCreate,
    IpAccessRuleResponse,
    IpCheckRequest,
    IpCheckResponse,
    PasswordCheckResponse,
    SecurityMetricsResponse,
    ThreatHitInfo,
    VulnerabilityCreate,
    VulnerabilityResponse,
    VulnerabilityStats,
    VulnerabilityUpdate,
)
from hscredit_studio.services.security_hardening import (
    PasswordStrength,
    check_ip_allowed,
    detect_suspicious_request,
    validate_password_complexity,
)
from hscredit_studio.services.soc import (
    aggregate_security_metrics,
    create_vulnerability,
    export_events_cef,
    export_events_csv,
    export_events_syslog,
    list_vulnerabilities,
    update_vulnerability_status,
    verify_recent_audit_chain,
)

router = APIRouter(tags=["安全"])


# ===== SOC 仪表板 =====


@router.get("/metrics", summary="安全运营指标")
async def security_metrics(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    window_days: int = Query(default=7, ge=1, le=90),
) -> SecurityMetricsResponse:
    """Phase 5 B25 — SOC 仪表板指标 (总事件/失败登录/数据导出 等)."""
    tid = UUID(tenant_id)
    m = await aggregate_security_metrics(session, tenant_id=tid, window_days=window_days)
    return SecurityMetricsResponse(
        total_events=m.total_events,
        failed_logins=m.failed_logins,
        auth_failures=m.auth_failures,
        sensitive_data_access=m.sensitive_data_access,
        data_exports=m.data_exports,
        permission_changes=m.permission_changes,
        config_changes=m.config_changes,
        top_actions=m.top_actions,
        top_ips=m.top_ips,
        window_days=m.window_days,
        generated_at=m.generated_at,
    )


@router.get("/audit-integrity", summary="审计链完整性检查")
async def audit_integrity(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    hours: int = Query(default=24, ge=1, le=720),
) -> dict[str, Any]:
    """Phase 5 B25 — 检查最近 N 小时审计链完整性."""
    tid = UUID(tenant_id)
    secret = getattr(settings, "audit_chain_secret", "") or ""
    result = await verify_recent_audit_chain(
        session, tenant_id=tid, hours=hours, secret=secret
    )
    return {
        "is_valid": result.is_valid,
        "checked_count": result.checked_count,
        "failed_event_id": result.failed_event_id,
        "error": result.error,
        "checked_at": result.checked_at,
    }


# ===== SIEM 导出 =====


@router.get("/export", summary="审计日志 SIEM 导出")
async def siem_export(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    format: str = Query(default="cef", pattern="^(cef|syslog|csv)$"),
    hours: int = Query(default=24, ge=1, le=720),
) -> dict[str, Any]:
    """Phase 5 B25 — 导出审计日志供 SIEM 集成 (Splunk/QRadar/Elastic)."""
    tid = UUID(tenant_id)
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        await session.execute(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tid, AuditEvent.occurred_at >= since)
            .order_by(AuditEvent.occurred_at.asc())
        )
    ).scalars().all()
    events = [
        {
            "event_id": str(r.event_id),
            "tenant_id": str(r.tenant_id),
            "user_id": str(r.user_id) if r.user_id else "",
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": str(r.resource_id) if r.resource_id else "",
            "ip_address": str(r.ip_address) if r.ip_address else "",
            "user_agent": r.user_agent or "",
            "details": r.details or {},
            "occurred_at": r.occurred_at,
        }
        for r in rows
    ]
    if format == "cef":
        content = export_events_cef(events)
    elif format == "syslog":
        content = export_events_syslog(events)
    else:
        content = export_events_csv(events).decode("utf-8")
    return {"format": format, "event_count": len(events), "content": content}


# ===== 入侵检测 =====


@router.post("/intrusion-check", summary="入侵检测 (WAF)")
async def intrusion_check(
    body: IntrusionCheckRequest = Body(...),
) -> IntrusionCheckResponse:
    """Phase 5 B25 — 对单次请求做入侵检测 (供中间件/前端调试用).

    检测 SQL 注入 / XSS / 路径遍历 / 命令注入 / LDAP 注入.
    """
    hits = detect_suspicious_request(
        path=body.path,
        query=body.query,
        body=body.body,
        user_agent=body.user_agent,
    )
    return IntrusionCheckResponse(
        is_safe=len(hits) == 0,
        hits=[
            ThreatHitInfo(
                threat_type=h.threat_type.value,
                pattern=h.pattern,
                location=h.location,
            )
            for h in hits
        ],
    )


# ===== 密码复杂度 =====


@router.post("/password-check", summary="密码复杂度校验")
async def password_check(password: str = Body(..., embed=True)) -> PasswordCheckResponse:
    """Phase 5 B25 — 等保三级密码复杂度校验."""
    strength = validate_password_complexity(password)
    return PasswordCheckResponse(
        strength=strength.value,
        is_acceptable=strength in (PasswordStrength.MEDIUM, PasswordStrength.STRONG),
    )


# ===== IP 访问规则 =====


@router.get(
    "/ip-rules",
    summary="IP 黑白名单",
    response_model=list[IpAccessRuleResponse],
)
async def list_ip_rules(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    rule_type: str | None = Query(default=None, pattern="^(whitelist|blacklist)$"),
) -> list[IpAccessRuleResponse]:
    """列出租户 IP 规则."""
    tid = UUID(tenant_id)
    stmt = select(IpAccessRule).where(IpAccessRule.tenant_id == tid)
    if rule_type:
        stmt = stmt.where(IpAccessRule.rule_type == rule_type)
    stmt = stmt.order_by(IpAccessRule.created_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return [
        IpAccessRuleResponse(
            rule_id=str(r.rule_id),
            tenant_id=str(r.tenant_id),
            rule_type=r.rule_type,
            cidr=r.cidr,
            description=r.description,
            enabled=r.enabled,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.post("/ip-rules", summary="新增 IP 规则")
async def add_ip_rule(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    body: IpAccessRuleCreate = Body(...),
) -> IpAccessRuleResponse:
    """新增租户 IP 访问规则 (白/黑名单)."""
    tid = UUID(tenant_id)
    # 校验 CIDR 格式
    if "/" in body.cidr:
        try:
            from ipaddress import ip_network

            ip_network(body.cidr, strict=False)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"CIDR 格式错误: {e}") from e
    rule = IpAccessRule(
        tenant_id=tid,
        rule_type=body.rule_type,
        cidr=body.cidr,
        description=body.description,
        enabled=body.enabled,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return IpAccessRuleResponse(
        rule_id=str(rule.rule_id),
        tenant_id=str(rule.tenant_id),
        rule_type=rule.rule_type,
        cidr=rule.cidr,
        description=rule.description,
        enabled=rule.enabled,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.delete("/ip-rules/{rule_id}", summary="删除 IP 规则")
async def delete_ip_rule(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    rule_id: str,
) -> dict[str, Any]:
    """删除 IP 访问规则."""
    tid = UUID(tenant_id)
    rid = UUID(rule_id)
    rule = await session.get(IpAccessRule, rid)
    if rule is None or rule.tenant_id != tid:
        raise HTTPException(status_code=404, detail="规则不存在")
    await session.delete(rule)
    await session.commit()
    return {"deleted": rule_id}


@router.post("/ip-check", summary="IP 访问检查")
async def ip_check(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    body: IpCheckRequest = Body(...),
) -> IpCheckResponse:
    """检查指定 IP 是否被允许访问本租户.

    综合白/黑名单规则, 给出决策结果.
    """
    tid = UUID(tenant_id)
    # 读取所有启用的规则
    rows = (
        await session.execute(
            select(IpAccessRule).where(
                IpAccessRule.tenant_id == tid, IpAccessRule.enabled.is_(True)
            )
        )
    ).scalars().all()
    whitelist = [r.cidr for r in rows if r.rule_type == "whitelist"]
    blacklist = [r.cidr for r in rows if r.rule_type == "blacklist"]
    decision = check_ip_allowed(body.ip, whitelist=whitelist, blacklist=blacklist)
    return IpCheckResponse(
        ip=body.ip,
        allowed=decision.allowed,
        reason=decision.reason,
        matched_rule=decision.matched_rule,
    )


# ===== 渗透测试发现 =====


@router.get(
    "/vulnerabilities",
    summary="漏洞列表",
    response_model=list[VulnerabilityResponse],
)
async def list_vulnerabilities_endpoint(
    session: SessionDep,
    _: CurrentUserDep,
    status: str | None = Query(default=None, pattern="^(open|in_progress|closed|wont_fix)$"),
    severity: str | None = Query(default=None, pattern="^(low|medium|high|critical)$"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[VulnerabilityResponse]:
    """Phase 5 B25 — 列出渗透测试发现项."""
    vulns = await list_vulnerabilities(
        session, status=status, severity=severity, limit=limit
    )
    return [
        VulnerabilityResponse(
            vuln_id=str(v.vuln_id),
            title=v.title,
            severity=v.severity,
            description=v.description,
            remediation=v.remediation,
            status=v.status,
            discovered_at=v.discovered_at,
            closed_at=v.closed_at,
            fix_notes=v.fix_notes,
            source=v.source,
        )
        for v in vulns
    ]


@router.post("/vulnerabilities", summary="登记漏洞")
async def add_vulnerability(
    session: SessionDep,
    _: CurrentUserDep,
    body: VulnerabilityCreate = Body(...),
) -> VulnerabilityResponse:
    """登记新发现的渗透测试 / 自查漏洞."""
    v = await create_vulnerability(
        session,
        title=body.title,
        severity=body.severity,
        description=body.description,
        remediation=body.remediation,
    )
    return VulnerabilityResponse(
        vuln_id=str(v.vuln_id),
        title=v.title,
        severity=v.severity,
        description=v.description,
        remediation=v.remediation,
        status=v.status,
        discovered_at=v.discovered_at,
        closed_at=v.closed_at,
        fix_notes=v.fix_notes,
        source=v.source,
    )


@router.patch("/vulnerabilities/{vuln_id}", summary="更新漏洞状态")
async def patch_vulnerability(
    session: SessionDep,
    _: CurrentUserDep,
    vuln_id: str,
    body: VulnerabilityUpdate = Body(...),
) -> VulnerabilityResponse:
    """更新漏洞处置状态 (open → in_progress → closed/wont_fix)."""
    vid = UUID(vuln_id)
    v = await update_vulnerability_status(
        session, vuln_id=vid, status=body.status, fix_notes=body.fix_notes
    )
    if v is None:
        raise HTTPException(status_code=404, detail="漏洞不存在")
    return VulnerabilityResponse(
        vuln_id=str(v.vuln_id),
        title=v.title,
        severity=v.severity,
        description=v.description,
        remediation=v.remediation,
        status=v.status,
        discovered_at=v.discovered_at,
        closed_at=v.closed_at,
        fix_notes=v.fix_notes,
        source=v.source,
    )


@router.get("/vulnerabilities/stats", summary="漏洞统计")
async def vulnerability_stats(
    session: SessionDep,
    _: CurrentUserDep,
) -> VulnerabilityStats:
    """Phase 5 B25 等保验收 — 漏洞关闭率统计."""
    rows = (
        await session.execute(
            select(Vulnerability.severity, Vulnerability.status, func.count(Vulnerability.vuln_id))
            .group_by(Vulnerability.severity, Vulnerability.status)
        )
    ).all()
    by_severity: dict[str, int] = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    open_n = in_progress_n = closed_n = wont_fix_n = 0
    for r in rows:
        sev = str(r.severity)
        st = str(r.status)
        cnt = int(r[2])
        by_severity[sev] = by_severity.get(sev, 0) + cnt
        if st == "open":
            open_n += cnt
        elif st == "in_progress":
            in_progress_n += cnt
        elif st == "closed":
            closed_n += cnt
        elif st == "wont_fix":
            wont_fix_n += cnt
    total = open_n + in_progress_n + closed_n + wont_fix_n
    closure_rate = (closed_n + wont_fix_n) / total if total > 0 else 1.0
    return VulnerabilityStats(
        total=total,
        open=open_n,
        in_progress=in_progress_n,
        closed=closed_n,
        wont_fix=wont_fix_n,
        closure_rate=round(closure_rate, 4),
        by_severity=by_severity,
    )


__all__ = ["router"]
