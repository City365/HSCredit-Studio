"""PIPL 数据保护合规相关模型 — Phase 5 B26.

依据 docs/ROADMAP.md Phase 5 B26:

> 数据流图 + 合法性基础（同意 / 合同 / 法定）
> 用户权利实现: 查询、更正、删除、可携
> 跨境传输审批流（如适用）
> 隐私政策中文版 + 同意弹窗

表设计:

- ``consent_records`` — 用户对各处理目的的同意记录 (撤回轨迹完整)
- ``data_subject_requests`` — 数据主体请求 (DSR) 审批工作流
- ``cross_border_transfers`` — 跨境数据传输审批流
- ``privacy_policy_versions`` — 隐私政策版本 (用户必须对最新版本重授权)

设计原则: 所有删除操作默认是**匿名化 (字段置 NULL)** 而非物理 DELETE,
保留可审计性.
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
from hscredit_studio.models.base import TenantMixin, TimestampMixin

# 同意目的 — 平台默认枚举 (实际项目可能扩展)
CONSENT_PURPOSE_VALUES = (
    "service_provision",  # 服务提供必需 (登录 / 工作流 / 用量)
    "billing",  # 账单 / 支付 / 合同
    "marketing",  # 营销通知 (可选)
    "analytics",  # 使用分析与改进 (可选)
    "third_party_sharing",  # 第三方共享 (可选)
)

# 数据主体请求类型
DSR_TYPE_VALUES = (
    "access",  # 查询 (PIPL 第 44 条)
    "correction",  # 更正 (第 46 条)
    "deletion",  # 删除 (第 47 条)
    "portability",  # 可携 (第 45 条)
    "withdraw_consent",  # 撤回同意 (第 29 条)
)

DSR_STATUS_VALUES = (
    "submitted",  # 已提交
    "verifying",  # 核验身份中
    "in_progress",  # 处理中
    "completed",  # 已完成
    "rejected",  # 拒绝
    "expired",  # 超期 (30 天法定时限)
)

# 跨境传输法律基础 (PIPL 第 38 条)
CROSS_BORDER_BASIS_VALUES = (
    "cac_assessment",  # 通过 CAC 安全评估
    "standard_contract",  # 标准合同备案
    "certification",  # 个人信息保护认证
    "explicit_consent",  # 单独同意
)


class ConsentRecord(Base, TimestampMixin, TenantMixin):
    """用户对某处理目的的同意记录 — Phase 5 B26.

    用户撤回同意时, **不删行**而是更新 ``revoked_at``.
    这样审计可完整回溯"何时同意 → 何时撤回".
    """

    __tablename__ = "consent_records"

    consent_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        comment="用户 ID (跨租户全局唯一)",
    )
    purpose: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=f"处理目的 {CONSENT_PURPOSE_VALUES}",
    )
    granted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        comment="是否同意",
    )
    policy_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'v1.0'"),
        comment="对应的隐私政策版本",
    )
    granted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="同意时间",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="撤回时间, NULL=当前仍有效",
    )
    source: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="同意来源 (web_register / api / admin_manual)",
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="同意时的浏览器 UA",
    )

    __table_args__ = (
        Index("ix_consent_user_purpose", "user_id", "purpose"),
        Index("ix_consent_tenant_granted", "tenant_id", "granted"),
        Index("ix_consent_revoked", "revoked_at"),
    )


class DataSubjectRequest(Base, TimestampMixin, TenantMixin):
    """数据主体请求 (DSR) — Phase 5 B26.

    PIPL 第 50 条: 收到请求后 30 天内处理 (特殊可延长至 60 天).

    字段:
    - request_type: access / correction / deletion / portability
    - status: 流转状态
    - payload: 请求具体内容 (待更正字段 / 导出范围等)
    - response: 处理结果 (导出文件 ID / 更正前后 diff / 删除 ID 列表)
    """

    __tablename__ = "data_subject_requests"

    request_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        comment="申请人用户 ID",
    )
    request_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment=f"请求类型 {DSR_TYPE_VALUES}",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'submitted'"),
        comment=f"状态 {DSR_STATUS_VALUES}",
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="用户提交的原因 / 补充信息",
    )
    payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="请求参数 (待更正字段 / 导出范围等)",
    )
    response: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="处理结果",
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="提交时间 (法定 30 天起算点)",
    )
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="法定截止时间 (submitted_at + 30 天)",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="实际完成时间",
    )
    processor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="处理人 (DPA/Admin) user_id",
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="拒绝原因 (如身份核验失败)",
    )

    __table_args__ = (
        Index("ix_dsr_user_type", "tenant_id", "user_id", "request_type"),
        Index("ix_dsr_status", "tenant_id", "status"),
        Index("ix_dsr_due_at", "due_at"),
    )


class CrossBorderTransfer(Base, TimestampMixin, TenantMixin):
    """跨境数据传输审批流 — Phase 5 B26.

    PIPL 第 38 条: 跨境传输必须满足以下之一:
    - 通过 CAC 安全评估
    - 标准合同备案
    - 个人信息保护认证
    - 单独同意

    本表用于记录每次跨境传输及其法律基础.
    """

    __tablename__ = "cross_border_transfers"

    transfer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="关联用户 (NULL=批量导出)",
    )
    destination_country: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        comment="目标国家 ISO 3166-1 alpha-2 (US / SG / JP)",
    )
    destination_entity: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        comment="接收方 (AWS US-East / Google Cloud 等)",
    )
    data_categories: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="传输的字段分类 (如 [HIGHLY_SENSITIVE.id_card])",
    )
    legal_basis: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=f"法律基础 {CROSS_BORDER_BASIS_VALUES}",
    )
    legal_basis_ref: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        comment="依据文件编号 (CAC 评估编号 / 合同号 / 认证号)",
    )
    approved: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="审批状态 (NULL=待审, True=批准, False=拒绝)",
    )
    approver_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="审批人 (DPA)",
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="审批时间",
    )

    __table_args__ = (
        Index("ix_cross_border_destination", "destination_country"),
        Index("ix_cross_border_status", "approved"),
        Index("ix_cross_border_user", "user_id"),
    )


class PrivacyPolicyVersion(Base, TimestampMixin):
    """隐私政策版本管理 — Phase 5 B26.

    新版本上线时, 现有用户需重新同意 (即新增 consent_records 行).
    """

    __tablename__ = "privacy_policy_versions"

    version: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        comment="版本号 (semver, 如 v1.0 / v1.1)",
    )
    title: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        comment="版本标题",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="政策正文 (中文)",
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="生效时间",
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        comment="是否当前生效",
    )

    __table_args__ = (Index("ix_privacy_policy_current", "is_current"),)


__all__ = [
    "CONSENT_PURPOSE_VALUES",
    "CROSS_BORDER_BASIS_VALUES",
    "DSR_STATUS_VALUES",
    "DSR_TYPE_VALUES",
    "ConsentRecord",
    "CrossBorderTransfer",
    "DataSubjectRequest",
    "PrivacyPolicyVersion",
]
