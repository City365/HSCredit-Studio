"""安全加固相关数据模型 — Phase 5 B25.

依据 docs/ROADMAP.md Phase 5 B25:

> 等保差距整改（认证 / 访问控制 / 安全审计 / 入侵防范 / 数据保护 / 备份恢复）
> 渗透测试报告闭环

表设计:

- ``ip_access_rules`` — 租户级 IP 白/黑名单 (访问控制)
- ``account_lockouts`` — 登录失败锁定记录 (认证加固)
- ``vulnerabilities`` — 渗透测试发现跟踪 (渗透测试闭环)
- ``audit_chain_checkpoints`` — 审计链完整性检查日志 (定期任务产物)

设计原则: 不存密文 / 不存敏感业务数据, 仅存元信息.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from hscredit_studio.core.database import Base
from hscredit_studio.models.base import TenantMixin, TimestampMixin

IP_RULE_TYPE_VALUES = ("whitelist", "blacklist")
ACCOUNT_LOCKOUT_STATUS_VALUES = ("active", "expired", "manual_reset")
VULNERABILITY_STATUS_VALUES = ("open", "in_progress", "closed", "wont_fix")
VULNERABILITY_SEVERITY_VALUES = ("low", "medium", "high", "critical")
CHAIN_CHECKPOINT_STATUS_VALUES = ("ok", "broken", "missing_secret")


class IpAccessRule(Base, TimestampMixin, TenantMixin):
    """租户级 IP 访问规则 — Phase 5 B25.

    用于等保"访问控制"层面: 限定哪些 IP (或网段) 可访问租户资源.
    黑白名单互斥 (一个 CIDR 不能同时在两种规则中).
    """

    __tablename__ = "ip_access_rules"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    rule_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=f"规则类型 {IP_RULE_TYPE_VALUES}",
    )
    cidr: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="CIDR 网段或单 IP",
    )
    description: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        comment="备注 (来源 / 申请人 / 失效日期)",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        comment="是否启用",
    )

    __table_args__ = (
        Index("ix_ip_access_rules_tenant_type", "tenant_id", "rule_type"),
        Index("ix_ip_access_rules_enabled", "tenant_id", "enabled"),
    )


class AccountLockout(Base, TimestampMixin, TenantMixin):
    """账号登录失败锁定记录 — Phase 5 B25.

    记录锁定触发时间 / 释放时间 / 失败次数.
    锁定中 (``locked_until > now``) 的账号拒绝登录.
    """

    __tablename__ = "account_lockouts"

    lockout_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="被锁定用户 ID",
    )
    email_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="用户邮箱 SHA256 (16 字符截断, 避免明文)",
    )
    failed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="窗口内累计失败次数",
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="锁定截止时间 (NULL=未锁定)",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'active'"),
        comment=f"状态 {ACCOUNT_LOCKOUT_STATUS_VALUES}",
    )
    last_ip: Mapped[str | None] = mapped_column(
        INET,
        nullable=True,
        comment="触发锁定的最后 IP",
    )

    __table_args__ = (
        Index("ix_account_lockouts_user", "tenant_id", "user_id"),
        Index("ix_account_lockouts_email", "tenant_id", "email_hash"),
        Index("ix_account_lockouts_until", "locked_until"),
    )


class Vulnerability(Base, TimestampMixin):
    """渗透测试 / 安全评估发现项 — Phase 5 B25.

    用于跟踪第三方渗透测试报告中的发现项及修复进度.
    整改项关闭率 = closed / (open + in_progress + closed),
    等保验收要求关闭率 100% (含 wont_fix).
    """

    __tablename__ = "vulnerabilities"

    vuln_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    title: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        comment="发现项标题",
    )
    severity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=f"严重级别 {VULNERABILITY_SEVERITY_VALUES}",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="详细描述 (含复现步骤 / 风险说明)",
    )
    remediation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="修复建议",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'open'"),
        comment=f"状态 {VULNERABILITY_STATUS_VALUES}",
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="发现时间",
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="关闭时间",
    )
    fix_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="修复说明 / 验证结果",
    )
    source: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="来源 (例: pentest_2026Q3 / self_audit / bug_bounty)",
    )

    __table_args__ = (
        Index("ix_vulnerabilities_status", "status"),
        Index("ix_vulnerabilities_severity", "severity"),
        Index("ix_vulnerabilities_discovered", "discovered_at"),
    )


class AuditChainCheckpoint(Base):
    """审计链完整性检查日志 — Phase 5 B25.

    定时任务 (cron) 调用 :func:`verify_recent_audit_chain`, 结果落入此表.
    SOC 告警规则: 最近一次状态为 broken 即触发.
    """

    __tablename__ = "audit_chain_checkpoints"

    checkpoint_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="限定租户 (NULL=全平台检查)",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=f"检查结果 {CHAIN_CHECKPOINT_STATUS_VALUES}",
    )
    checked_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="检查事件数",
    )
    failed_event_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="失败的事件 ID (status=broken 时)",
    )
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="错误信息",
    )
    window_hours: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("24"),
        comment="检查时间窗口 (小时)",
    )
    details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="扩展元数据",
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="检查时间",
    )

    __table_args__ = (
        Index("ix_audit_chain_checkpoints_status", "status"),
        Index("ix_audit_chain_checkpoints_checked_at", "checked_at"),
        Index("ix_audit_chain_checkpoints_tenant", "tenant_id"),
    )


__all__ = [
    "ACCOUNT_LOCKOUT_STATUS_VALUES",
    "CHAIN_CHECKPOINT_STATUS_VALUES",
    "IP_RULE_TYPE_VALUES",
    "VULNERABILITY_SEVERITY_VALUES",
    "VULNERABILITY_STATUS_VALUES",
    "AccountLockout",
    "AuditChainCheckpoint",
    "IpAccessRule",
    "Vulnerability",
]
