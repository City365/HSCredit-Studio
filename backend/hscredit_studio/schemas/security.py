"""安全加固 Schema — Phase 5 B25.

依据 docs/ROADMAP.md Phase 5 B25:

> 等保差距整改（认证 / 访问控制 / 安全审计 / 入侵防范 / 数据保护 / 备份恢复）
> 渗透测试报告闭环
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ===== IP 访问规则 =====


class IpAccessRuleCreate(BaseModel):
    """新增 IP 访问规则请求."""

    model_config = ConfigDict(from_attributes=True)

    rule_type: str = Field(..., pattern="^(whitelist|blacklist)$", description="规则类型")
    cidr: str = Field(..., min_length=1, max_length=64, description="CIDR 网段")
    description: str | None = Field(default=None, max_length=256)
    enabled: bool = Field(default=True)


class IpAccessRuleResponse(BaseModel):
    """IP 访问规则响应."""

    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    tenant_id: str
    rule_type: str
    cidr: str
    description: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class IpCheckRequest(BaseModel):
    """IP 访问控制检查请求."""

    model_config = ConfigDict(from_attributes=True)

    ip: str = Field(..., description="待检查 IP")


class IpCheckResponse(BaseModel):
    """IP 访问控制检查响应."""

    model_config = ConfigDict(from_attributes=True)

    ip: str
    allowed: bool
    reason: str
    matched_rule: str | None


# ===== 账号锁定 =====


class LockoutStateResponse(BaseModel):
    """锁定状态响应."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str | None
    email_hash: str | None
    failed_count: int
    is_locked: bool
    locked_until: datetime | None
    status: str


# ===== 渗透测试发现 =====


class VulnerabilityCreate(BaseModel):
    """登记渗透测试发现项."""

    model_config = ConfigDict(from_attributes=True)

    title: str = Field(..., max_length=256)
    severity: str = Field(..., pattern="^(low|medium|high|critical)$")
    description: str
    remediation: str
    source: str | None = Field(default=None, max_length=128)


class VulnerabilityUpdate(BaseModel):
    """更新渗透测试发现项状态."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., pattern="^(open|in_progress|closed|wont_fix)$")
    fix_notes: str | None = None


class VulnerabilityResponse(BaseModel):
    """渗透测试发现项响应."""

    model_config = ConfigDict(from_attributes=True)

    vuln_id: str
    title: str
    severity: str
    description: str
    remediation: str
    status: str
    discovered_at: datetime
    closed_at: datetime | None
    fix_notes: str | None
    source: str | None


class VulnerabilityStats(BaseModel):
    """漏洞统计 — Phase 5 B25 等保验收.

    关闭率 = (closed + wont_fix) / total.
    等保要求: critical / high 关闭率 = 100%.
    """

    model_config = ConfigDict(from_attributes=True)

    total: int
    open: int
    in_progress: int
    closed: int
    wont_fix: int
    closure_rate: float
    by_severity: dict[str, int]


# ===== 审计链完整性 =====


class ChainCheckResponse(BaseModel):
    """审计链检查响应."""

    model_config = ConfigDict(from_attributes=True)

    is_valid: bool
    checked_count: int
    failed_event_id: str | None
    error: str | None
    checked_at: str


# ===== 安全指标 =====


class SecurityMetricsResponse(BaseModel):
    """安全运营指标响应."""

    model_config = ConfigDict(from_attributes=True)

    total_events: int
    failed_logins: int
    auth_failures: int
    sensitive_data_access: int
    data_exports: int
    permission_changes: int
    config_changes: int
    top_actions: list[tuple[str, int]] = Field(default_factory=list)
    top_ips: list[tuple[str, int]] = Field(default_factory=list)
    window_days: int
    generated_at: str


# ===== SIEM 导出 =====


class SiemExportRequest(BaseModel):
    """SIEM 导出请求."""

    model_config = ConfigDict(from_attributes=True)

    format: str = Field(default="cef", pattern="^(cef|syslog|csv)$")
    hours: int = Field(default=24, ge=1, le=720, description="导出最近 N 小时事件")


class SiemExportResponse(BaseModel):
    """SIEM 导出响应."""

    model_config = ConfigDict(from_attributes=True)

    format: str
    event_count: int
    content: str = Field(description="CEF / syslog / csv 内容")


# ===== 入侵检测 =====


class IntrusionCheckRequest(BaseModel):
    """入侵检测请求 (供中间件使用)."""

    model_config = ConfigDict(from_attributes=True)

    path: str = ""
    query: str = ""
    body: str = ""
    user_agent: str = ""


class ThreatHitInfo(BaseModel):
    """威胁命中详情."""

    model_config = ConfigDict(from_attributes=True)

    threat_type: str
    pattern: str
    location: str


class IntrusionCheckResponse(BaseModel):
    """入侵检测响应."""

    model_config = ConfigDict(from_attributes=True)

    is_safe: bool
    hits: list[ThreatHitInfo]


# ===== 密码复杂度 =====


class PasswordCheckResponse(BaseModel):
    """密码复杂度校验响应."""

    model_config = ConfigDict(from_attributes=True)

    strength: str = Field(description="invalid/weak/medium/strong")
    is_acceptable: bool = Field(description="是否可接受 (≥ medium)")


__all__ = [
    "ChainCheckResponse",
    "IntrusionCheckRequest",
    "IntrusionCheckResponse",
    "IpAccessRuleCreate",
    "IpAccessRuleResponse",
    "IpCheckRequest",
    "IpCheckResponse",
    "LockoutStateResponse",
    "PasswordCheckResponse",
    "SecurityMetricsResponse",
    "SiemExportRequest",
    "SiemExportResponse",
    "ThreatHitInfo",
    "VulnerabilityCreate",
    "VulnerabilityResponse",
    "VulnerabilityStats",
    "VulnerabilityUpdate",
]
