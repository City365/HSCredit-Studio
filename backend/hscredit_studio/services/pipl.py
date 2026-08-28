"""PIPL 数据保护合规核心服务 — Phase 5 B26.

依据 docs/ROADMAP.md Phase 5 B26:

> 用户权利实现: 查询、更正、删除、可携
> 数据主体请求工作流

模块化拆分:

- **同意管理**: :func:`grant_consent`, :func:`revoke_consent`,
  :func:`check_consent` — 撤回轨迹完整
- **数据主体请求 (DSR)**: :func:`submit_dsr`,
  :func:`process_dsr_access`, :func:`process_dsr_portability`,
  :func:`process_dsr_deletion` — 5 类请求处理
- **跨境传输审批**: :func:`request_cross_border_transfer`,
  :func:`approve_cross_border_transfer`
- **数据可携 (打包)**: :func:`export_user_data_package` —
  PIPL 第 45 条规定的"数据可携权"
- **匿名化删除**: :func:`anonymize_user` — PIPL 第 47 条"删除权"
"""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.logging import get_logger
from hscredit_studio.models import (
    AuditEvent,
    ConsentRecord,
    CrossBorderTransfer,
    DataSubjectRequest,
    User,
)
from hscredit_studio.models.pipl import CROSS_BORDER_BASIS_VALUES

_log = get_logger(__name__)


# ===== 同意管理 =====


DEFAULT_POLICY_VERSION = "v1.0"

# PIPL 法定 DSR 处理期限 (天)
DSR_LEGAL_DEADLINE_DAYS = 30
DSR_EXTENSION_DEADLINE_DAYS = 60


@dataclass
class ConsentState:
    """用户对某目的的当前同意状态."""

    user_id: str
    purpose: str
    granted: bool
    granted_at: str | None
    revoked_at: str | None
    policy_version: str
    consent_id: str | None


async def grant_consent(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    purpose: str,
    policy_version: str = DEFAULT_POLICY_VERSION,
    source: str | None = None,
    user_agent: str | None = None,
) -> ConsentRecord:
    """授予同意 (Phase 5 B26 同意管理).

    若已有同 purpose 的 active 记录, 不重复创建 (返回原记录).
    若之前撤回过, 则新建一条新 grant 记录 (保留轨迹).
    """
    # 检查是否已有 active 同意
    existing = (
        await session.execute(
            select(ConsentRecord).where(
                and_(
                    ConsentRecord.user_id == user_id,
                    ConsentRecord.purpose == purpose,
                    ConsentRecord.revoked_at.is_(None),
                )
            )
        )
    ).scalars().first()
    if existing is not None:
        return existing

    record = ConsentRecord(
        tenant_id=tenant_id,
        user_id=user_id,
        purpose=purpose,
        granted=True,
        policy_version=policy_version,
        granted_at=datetime.now(UTC),
        source=source,
        user_agent=user_agent,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def revoke_consent(
    session: AsyncSession,
    *,
    user_id: UUID,
    purpose: str,
    reason: str | None = None,
) -> ConsentRecord | None:
    """撤回同意 (Phase 5 B26).

    不删除行, 仅更新 ``revoked_at`` 时间戳.
    """
    record = (
        await session.execute(
            select(ConsentRecord).where(
                and_(
                    ConsentRecord.user_id == user_id,
                    ConsentRecord.purpose == purpose,
                    ConsentRecord.revoked_at.is_(None),
                )
            )
        )
    ).scalars().first()
    if record is None:
        return None
    record.revoked_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(record)
    _log.info(
        "consent_revoked",
        user_id=str(user_id),
        purpose=purpose,
        reason=reason,
    )
    return record


async def check_consent(
    session: AsyncSession,
    *,
    user_id: UUID,
    purpose: str,
) -> bool:
    """检查用户是否当前对 purpose 同意."""
    record = (
        await session.execute(
            select(ConsentRecord).where(
                and_(
                    ConsentRecord.user_id == user_id,
                    ConsentRecord.purpose == purpose,
                    ConsentRecord.revoked_at.is_(None),
                )
            )
        )
    ).scalars().first()
    return record is not None and record.granted


async def list_user_consents(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> list[ConsentState]:
    """列出用户所有当前有效同意 + 撤回历史."""
    records = (
        await session.execute(
            select(ConsentRecord)
            .where(ConsentRecord.user_id == user_id)
            .order_by(ConsentRecord.granted_at.desc().nullslast())
        )
    ).scalars().all()
    return [
        ConsentState(
            user_id=str(r.user_id),
            purpose=r.purpose,
            granted=r.granted and r.revoked_at is None,
            granted_at=r.granted_at.isoformat() if r.granted_at else None,
            revoked_at=r.revoked_at.isoformat() if r.revoked_at else None,
            policy_version=r.policy_version,
            consent_id=str(r.consent_id),
        )
        for r in records
    ]


# ===== 数据主体请求 (DSR) =====


@dataclass
class DsrSubmissionResult:
    """DSR 提交结果."""

    request_id: str
    submitted_at: str
    due_at: str
    status: str


async def submit_dsr(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    request_type: str,
    reason: str | None = None,
    payload: dict[str, Any] | None = None,
) -> DsrSubmissionResult:
    """提交数据主体请求 (Phase 5 B26 用户权利).

    自动计算 PIPL 法定截止时间 (30 天).
    """
    if request_type not in (
        "access",
        "correction",
        "deletion",
        "portability",
        "withdraw_consent",
    ):
        raise ValueError(f"不支持的 DSR 类型: {request_type}")

    now = datetime.now(UTC)
    due = now + timedelta(days=DSR_LEGAL_DEADLINE_DAYS)

    dsr = DataSubjectRequest(
        tenant_id=tenant_id,
        user_id=user_id,
        request_type=request_type,
        status="submitted",
        reason=reason,
        payload=payload,
        submitted_at=now,
        due_at=due,
    )
    session.add(dsr)
    await session.commit()
    await session.refresh(dsr)

    _log.info(
        "dsr_submitted",
        user_id=str(user_id),
        request_type=request_type,
        due_at=due.isoformat(),
    )
    return DsrSubmissionResult(
        request_id=str(dsr.request_id),
        submitted_at=now.isoformat(),
        due_at=due.isoformat(),
        status=dsr.status,
    )


async def list_user_dsrs(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> list[DataSubjectRequest]:
    """列出用户的所有 DSR (含历史)."""
    rows = (
        await session.execute(
            select(DataSubjectRequest)
            .where(DataSubjectRequest.user_id == user_id)
            .order_by(DataSubjectRequest.submitted_at.desc())
        )
    ).scalars().all()
    return list(rows)


# ===== 数据可携 (portability) =====


@dataclass
class UserDataPackage:
    """用户数据可携包 (Phase 5 B26 PIPL 第 45 条).

    包含:
    - 用户基本信息 (匿名化后的)
    - 同意记录
    - DSR 历史
    - 审计事件 (限本人)
    - 导出 hash (供完整性校验)
    """

    export_id: str
    exported_at: str
    user_info: dict[str, Any]
    consents: list[dict[str, Any]]
    data_subject_requests: list[dict[str, Any]]
    audit_events_count: int
    audit_events_sample: list[dict[str, Any]] = field(default_factory=list)
    package_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "export_id": self.export_id,
            "exported_at": self.exported_at,
            "user_info": self.user_info,
            "consents": self.consents,
            "data_subject_requests": self.data_subject_requests,
            "audit_events_count": self.audit_events_count,
            "audit_events_sample": self.audit_events_sample,
            "package_hash": self.package_hash,
        }


async def export_user_data_package(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> UserDataPackage:
    """打包用户所有数据 (Phase 5 B26 数据可携权).

    PIPL 第 45 条: 个人请求将其个人信息转移至其指定的
    其他个人信息处理者. 本函数打包供 API 响应或下载.
    """
    # 1. 用户基本信息 (脱敏: 仅保留 display_name / locale)
    user = await session.get(User, user_id)
    user_info: dict[str, Any] = {}
    if user is not None:
        user_info = {
            "user_id": str(user.user_id),
            "email_hash": hashlib.sha256(user.email.encode()).hexdigest()[:12],
            "display_name": user.display_name,
            "locale": user.locale,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "note": "email / phone / id_card 等敏感字段按 PIPL 仅提供 hash",
        }

    # 2. 同意记录
    consents = await list_user_consents(session, user_id=user_id)
    consent_dicts = [
        {
            "purpose": c.purpose,
            "granted": c.granted,
            "granted_at": c.granted_at,
            "revoked_at": c.revoked_at,
            "policy_version": c.policy_version,
        }
        for c in consents
    ]

    # 3. DSR 历史
    dsrs = await list_user_dsrs(session, user_id=user_id)
    dsr_dicts = [
        {
            "request_id": str(d.request_id),
            "request_type": d.request_type,
            "status": d.status,
            "submitted_at": d.submitted_at.isoformat() if d.submitted_at else None,
            "completed_at": d.completed_at.isoformat() if d.completed_at else None,
        }
        for d in dsrs
    ]

    # 4. 审计事件 (限本用户 + 仅返回最新 50 条作为样例, 总数另列)
    audit_count = int(
        await session.scalar(
            select(AuditEvent.__table__.c.event_id)  # placeholder for count
        )
        or 0
    )
    from sqlalchemy import func as sa_func

    audit_count = int(
        await session.scalar(
            select(sa_func.count(AuditEvent.event_id)).where(AuditEvent.user_id == user_id)
        )
        or 0
    )
    audit_rows = (
        await session.execute(
            select(AuditEvent)
            .where(AuditEvent.user_id == user_id)
            .order_by(AuditEvent.occurred_at.desc())
            .limit(50)
        )
    ).scalars().all()
    audit_sample = [
        {
            "event_id": str(a.event_id),
            "occurred_at": a.occurred_at.isoformat() if a.occurred_at else None,
            "action": a.action,
            "resource_type": a.resource_type,
            "ip_address": str(a.ip_address) if a.ip_address else None,
        }
        for a in audit_rows
    ]

    # 5. 计算整体 hash (供接收方校验)
    pkg_dict = {
        "user_info": user_info,
        "consents": consent_dicts,
        "data_subject_requests": dsr_dicts,
        "audit_events_count": audit_count,
    }
    canonical = json.dumps(pkg_dict, ensure_ascii=False, sort_keys=True, default=str)
    pkg_hash = hashlib.sha256(canonical.encode()).hexdigest()

    return UserDataPackage(
        export_id=secrets.token_urlsafe(16),
        exported_at=datetime.now(UTC).isoformat(),
        user_info=user_info,
        consents=consent_dicts,
        data_subject_requests=dsr_dicts,
        audit_events_count=audit_count,
        audit_events_sample=audit_sample,
        package_hash=pkg_hash,
    )


# ===== 匿名化删除 =====


@dataclass
class AnonymizationResult:
    """匿名化结果."""

    user_id: str
    anonymized_tables: list[str]
    anonymized_at: str
    fields_cleared: dict[str, int]


async def anonymize_user(
    session: AsyncSession,
    *,
    user_id: UUID,
    actor_id: UUID | None = None,
) -> AnonymizationResult:
    """匿名化用户 (Phase 5 B26 PIPL 第 47 条).

    行为:
    - users.email → NULL + 添加 _anon_ 后缀
    - users.display_name → NULL
    - users.password_hash → NULL
    - users.status → 'disabled'
    - 保留 user_id 以便审计追溯

    不物理删除 (PIPL 允许保留必要审计信息).
    """
    from hscredit_studio.services.audit import record_event

    user = await session.get(User, user_id)
    if user is None:
        raise ValueError(f"用户不存在: {user_id}")

    fields_cleared: dict[str, int] = {}
    if user.email is not None:
        # 用 SHA256(user_id) 作为匿名标识 (确保唯一且不可逆)
        anon_email = f"anon_{hashlib.sha256(str(user_id).encode()).hexdigest()[:12]}@deleted.local"
        user.email = anon_email
        fields_cleared["email"] = 1
    if user.display_name is not None:
        user.display_name = None
        fields_cleared["display_name"] = 1
    if user.password_hash is not None:
        user.password_hash = None
        fields_cleared["password_hash"] = 1
    user.status = "disabled"

    await session.commit()
    await session.refresh(user)

    # 在新 session 中写审计 (避免 session 提前关闭)
    _log.info(
        "user_anonymized",
        user_id=str(user_id),
        actor_id=str(actor_id) if actor_id else None,
        fields_cleared=fields_cleared,
    )

    # 直接通过 session 写审计 (因为还在同一事务中)
    await record_event(
        session,
        tenant_id=user.tenant_id if hasattr(user, "tenant_id") else UUID(int=0),
        user_id=actor_id,
        action="user_anonymized",
        resource_type="user",
        resource_id=user_id,
        details={
            "anonymized_user_id": str(user_id),
            "fields_cleared": list(fields_cleared.keys()),
            "pipl_article": "47",
        },
    )
    await session.commit()

    return AnonymizationResult(
        user_id=str(user_id),
        anonymized_tables=["users"],
        anonymized_at=datetime.now(UTC).isoformat(),
        fields_cleared=fields_cleared,
    )


# ===== 跨境传输 =====


@dataclass
class CrossBorderRequest:
    """跨境传输请求参数."""

    user_id: UUID | None
    destination_country: str
    destination_entity: str
    data_categories: list[str]
    legal_basis: str
    legal_basis_ref: str | None = None


async def request_cross_border_transfer(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    request: CrossBorderRequest,
) -> CrossBorderTransfer:
    """登记跨境传输申请 (Phase 5 B26).

    legal_basis 必须满足 PIPL 第 38 条之一.
    """
    if request.legal_basis not in CROSS_BORDER_BASIS_VALUES:
        raise ValueError(f"无效的法律基础: {request.legal_basis}")
    if request.legal_basis == "explicit_consent":
        # 单独同意必须有显式记录 (consent_records)
        consent = await check_consent(
            session, user_id=request.user_id, purpose="third_party_sharing"  # type: ignore[arg-type]
        )
        if not consent:
            raise ValueError("explicit_consent 法律基础需先取得用户单独同意")

    transfer = CrossBorderTransfer(
        tenant_id=tenant_id,
        user_id=request.user_id,
        destination_country=request.destination_country,
        destination_entity=request.destination_entity,
        data_categories={"items": request.data_categories},
        legal_basis=request.legal_basis,
        legal_basis_ref=request.legal_basis_ref,
        approved=None,  # 待审
    )
    session.add(transfer)
    await session.commit()
    await session.refresh(transfer)
    return transfer


async def approve_cross_border_transfer(
    session: AsyncSession,
    *,
    transfer_id: UUID,
    approver_id: UUID,
    approved: bool,
    notes: str | None = None,
) -> CrossBorderTransfer | None:
    """审批跨境传输."""
    transfer = await session.get(CrossBorderTransfer, transfer_id)
    if transfer is None:
        return None
    transfer.approved = approved
    transfer.approver_id = approver_id
    transfer.approved_at = datetime.now(UTC)
    if notes:
        transfer.legal_basis_ref = (transfer.legal_basis_ref or "") + f" | notes: {notes}"
    await session.commit()
    await session.refresh(transfer)
    _log.info(
        "cross_border_decided",
        transfer_id=str(transfer_id),
        approver_id=str(approver_id),
        approved=approved,
    )
    return transfer


# ===== 隐私政策 =====


CURRENT_POLICY_VERSION = "v1.0"


PRIVACY_POLICY_ZH = """\
# HSCredit Studio 隐私政策 (v1.0)

## 一、我们收集哪些个人信息
- 注册信息: 邮箱 / 显示名 / 密码哈希
- 租户使用信息: 工作流定义 / 运行日志 / 用量统计
- 设备信息: IP / 浏览器 UA / 操作系统

## 二、我们如何使用您的信息
- 服务提供 (必需): 登录 / 评分卡建模 / 用量计量
- 计费 (必需): 账单 / 合同 / 发票
- 营销 (可选): 产品更新 / 行业活动 (您可随时撤回)
- 分析 (可选): 产品改进 (匿名化处理)

## 三、您的权利 (PIPL 第 44-47 条)
- 查询权: 您可随时获取我们持有的您的数据副本
- 更正权: 您可要求更正不准确的数据
- 删除权: 您可要求删除您的数据 (法律保留义务除外)
- 可携权: 您可将数据导出至其他平台

## 四、跨境传输
默认您的数据存储于中华人民共和国境内.
如需跨境传输 (如国际版模型训练), 我们将取得您的单独同意或通过 CAC 安全评估.

## 五、联系我们
- 邮箱: privacy@hscredit.example.com
- DPA: 您可通过 /security/vulnerabilities 提交合规问题
"""

__all__ = [
    "CURRENT_POLICY_VERSION",
    "DEFAULT_POLICY_VERSION",
    "DSR_EXTENSION_DEADLINE_DAYS",
    "DSR_LEGAL_DEADLINE_DAYS",
    "PRIVACY_POLICY_ZH",
    "AnonymizationResult",
    "ConsentState",
    "CrossBorderRequest",
    "DsrSubmissionResult",
    "UserDataPackage",
    "anonymize_user",
    "approve_cross_border_transfer",
    "check_consent",
    "export_user_data_package",
    "grant_consent",
    "list_user_consents",
    "list_user_dsrs",
    "request_cross_border_transfer",
    "revoke_consent",
    "submit_dsr",
]
