"""PIPL 数据保护合规 API — Phase 5 B26.

依据 docs/ROADMAP.md Phase 5 B26:

| 端点 | 方法 | 用途 |
|---|---|---|
| /pipl/consent | GET | 列出当前用户所有同意记录 |
| /pipl/consent | POST | 授予同意 |
| /pipl/consent | DELETE | 撤回同意 |
| /pipl/dsr | GET | 列出当前用户所有 DSR |
| /pipl/dsr | POST | 提交 DSR |
| /pipl/me/data-export | GET | 数据可携 (打包下载) |
| /pipl/me/anonymize | POST | 请求匿名化 |
| /pipl/cross-border | GET | 跨境传输列表 (DPA) |
| /pipl/cross-border | POST | 申请跨境传输 |
| /pipl/cross-border/{id}/approve | PATCH | 审批 (DPA) |
| /pipl/privacy-policy | GET | 当前隐私政策 |
"""
from __future__ import annotations

from datetime import UTC
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Query
from sqlalchemy import select

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep
from hscredit_studio.models import CrossBorderTransfer, DataSubjectRequest
from hscredit_studio.schemas.pipl import (
    AnonymizationResponse,
    ConsentGrantRequest,
    ConsentRevokeRequest,
    ConsentStateResponse,
    CrossBorderApproveRequest,
    CrossBorderRequestSchema,
    CrossBorderResponse,
    DsrListItem,
    DsrProcessRequest,
    DsrSubmitRequest,
    DsrSubmitResponse,
    PrivacyPolicyResponse,
    UserDataPackageResponse,
)
from hscredit_studio.services.pipl import (
    CROSS_BORDER_BASIS_VALUES,
    CURRENT_POLICY_VERSION,
    PRIVACY_POLICY_ZH,
    CrossBorderRequest,
    anonymize_user,
    approve_cross_border_transfer,
    check_consent,
    export_user_data_package,
    grant_consent,
    list_user_consents,
    list_user_dsrs,
    request_cross_border_transfer,
    revoke_consent,
    submit_dsr,
)

router = APIRouter(tags=["PIPL"])


def _user_id(current: dict) -> UUID:
    """JWT payload 用 ``sub`` 字段承载用户 UUID (见 services/auth._build_token_pair)."""
    uid = current.get("sub") or current.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="无效 token: 缺 user_id")
    return UUID(str(uid))


def _actor_id(current: dict) -> UUID:
    """处理人 (DPA/Admin) 的 user_id — 与 _user_id 同一字段."""
    return _user_id(current)


# ===== 同意 =====


@router.get("/consent", summary="我的同意记录", response_model=list[ConsentStateResponse])
async def list_my_consents(
    session: SessionDep,
    _: CurrentUserDep,
) -> list[ConsentStateResponse]:
    """Phase 5 B26 — 列出当前用户所有同意 + 撤回历史."""
    uid = _user_id(_)
    states = await list_user_consents(session, user_id=uid)
    return [ConsentStateResponse(**s.__dict__) for s in states]


@router.post("/consent", summary="授予同意")
async def grant_consent_endpoint(
    session: SessionDep,
    current: CurrentUserDep,
    body: ConsentGrantRequest = Body(...),
) -> ConsentStateResponse:
    """Phase 5 B26 — 授予对某处理目的的同意."""
    uid = _user_id(current)
    record = await grant_consent(
        session,
        tenant_id=UUID(current["tenant_id"]),
        user_id=uid,
        purpose=body.purpose,
        policy_version=body.policy_version,
        source=body.source or "api",
    )
    return ConsentStateResponse(
        user_id=str(record.user_id),
        purpose=record.purpose,
        granted=record.granted and record.revoked_at is None,
        granted_at=record.granted_at.isoformat() if record.granted_at else None,
        revoked_at=record.revoked_at.isoformat() if record.revoked_at else None,
        policy_version=record.policy_version,
        consent_id=str(record.consent_id),
    )


@router.delete("/consent", summary="撤回同意")
async def revoke_consent_endpoint(
    session: SessionDep,
    current: CurrentUserDep,
    body: ConsentRevokeRequest = Body(...),
) -> dict[str, Any]:
    """Phase 5 B26 — 撤回对某处理目的的同意 (PIPL 第 29 条)."""
    uid = _user_id(current)
    record = await revoke_consent(session, user_id=uid, purpose=body.purpose, reason=body.reason)
    if record is None:
        raise HTTPException(status_code=404, detail="未找到有效同意记录")
    return {
        "consent_id": str(record.consent_id),
        "purpose": record.purpose,
        "revoked_at": record.revoked_at.isoformat() if record.revoked_at else None,
    }


@router.get("/consent/check", summary="检查是否同意")
async def check_consent_endpoint(
    session: SessionDep,
    current: CurrentUserDep,
    purpose: str = Query(..., pattern="^(service_provision|billing|marketing|analytics|third_party_sharing)$"),
) -> dict[str, Any]:
    """检查当前用户对某 purpose 是否仍同意."""
    uid = _user_id(current)
    granted = await check_consent(session, user_id=uid, purpose=purpose)
    return {"purpose": purpose, "granted": granted}


# ===== 数据主体请求 (DSR) =====


@router.get("/dsr", summary="我的 DSR 列表", response_model=list[DsrListItem])
async def list_my_dsrs(
    session: SessionDep,
    _: CurrentUserDep,
) -> list[DsrListItem]:
    """Phase 5 B26 — 列出当前用户提交过的所有 DSR."""
    uid = _user_id(_)
    rows = await list_user_dsrs(session, user_id=uid)
    return [
        DsrListItem(
            request_id=str(d.request_id),
            request_type=d.request_type,
            status=d.status,
            reason=d.reason,
            submitted_at=d.submitted_at,
            due_at=d.due_at,
            completed_at=d.completed_at,
        )
        for d in rows
    ]


@router.post("/dsr", summary="提交 DSR", response_model=DsrSubmitResponse)
async def submit_dsr_endpoint(
    session: SessionDep,
    current: CurrentUserDep,
    body: DsrSubmitRequest = Body(...),
) -> DsrSubmitResponse:
    """Phase 5 B26 — 提交数据主体请求 (PIPL 第 44-47 条)."""
    tenant_id = UUID(current["tenant_id"])
    uid = _user_id(current)
    result = await submit_dsr(
        session,
        tenant_id=tenant_id,
        user_id=uid,
        request_type=body.request_type,
        reason=body.reason,
        payload=body.payload,
    )
    return DsrSubmitResponse(
        request_id=result.request_id,
        submitted_at=result.submitted_at,
        due_at=result.due_at,
        status=result.status,
    )


@router.patch("/dsr/{request_id}", summary="处理 DSR")
async def process_dsr_endpoint(
    session: SessionDep,
    current: CurrentUserDep,
    request_id: str,
    body: DsrProcessRequest = Body(...),
) -> DsrListItem:
    """Phase 5 B26 — DPA/Admin 处理 DSR (流转状态)."""
    rid = UUID(request_id)
    dsr = await session.get(DataSubjectRequest, rid)
    if dsr is None:
        raise HTTPException(status_code=404, detail="DSR 不存在")
    dsr.status = body.new_status
    if body.response:
        dsr.response = body.response
    if body.new_status == "completed":
        from datetime import datetime

        dsr.completed_at = datetime.now(UTC)
        dsr.processor_id = _actor_id(current)
    if body.new_status == "rejected" and body.rejection_reason:
        dsr.rejection_reason = body.rejection_reason
        dsr.processor_id = _actor_id(current)
    await session.commit()
    await session.refresh(dsr)
    return DsrListItem(
        request_id=str(dsr.request_id),
        request_type=dsr.request_type,
        status=dsr.status,
        reason=dsr.reason,
        submitted_at=dsr.submitted_at,
        due_at=dsr.due_at,
        completed_at=dsr.completed_at,
    )


# ===== 数据可携 =====


@router.get("/me/data-export", summary="数据可携 (PIPL 第 45 条)")
async def export_my_data(
    session: SessionDep,
    current: CurrentUserDep,
) -> UserDataPackageResponse:
    """Phase 5 B26 — 打包并返回本用户的所有数据 (可携权)."""
    uid = _user_id(current)
    pkg = await export_user_data_package(session, user_id=uid)
    return UserDataPackageResponse(**pkg.to_dict())


# ===== 匿名化 =====


@router.post("/me/anonymize", summary="请求匿名化 (PIPL 第 47 条)")
async def anonymize_me(
    session: SessionDep,
    current: CurrentUserDep,
) -> AnonymizationResponse:
    """Phase 5 B26 — 立即匿名化当前用户的所有 PII.

    不可逆, 但保留 user_id 以便审计追溯. PIPL 第 47 条规定的"删除权".
    """
    uid = _user_id(current)
    actor = _actor_id(current)
    result = await anonymize_user(session, user_id=uid, actor_id=actor)
    return AnonymizationResponse(
        user_id=result.user_id,
        anonymized_tables=result.anonymized_tables,
        anonymized_at=result.anonymized_at,
        fields_cleared=result.fields_cleared,
    )


# ===== 跨境传输 =====


@router.get("/cross-border", summary="跨境传输列表")
async def list_cross_border(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
) -> list[CrossBorderResponse]:
    """列出租户跨境传输记录."""
    tid = UUID(tenant_id)
    rows = (
        await session.execute(
            select(CrossBorderTransfer)
            .where(CrossBorderTransfer.tenant_id == tid)
            .order_by(CrossBorderTransfer.created_at.desc())
        )
    ).scalars().all()
    return [
        CrossBorderResponse(
            transfer_id=str(r.transfer_id),
            destination_country=r.destination_country,
            destination_entity=r.destination_entity,
            legal_basis=r.legal_basis,
            approved=r.approved,
            approver_id=str(r.approver_id) if r.approver_id else None,
            approved_at=r.approved_at,
        )
        for r in rows
    ]


@router.post("/cross-border", summary="申请跨境传输")
async def request_cross_border_endpoint(
    session: SessionDep,
    current: CurrentUserDep,
    body: CrossBorderRequestSchema = Body(...),
) -> CrossBorderResponse:
    """Phase 5 B26 — 申请跨境数据传输 (PIPL 第 38 条)."""
    tenant_id = UUID(current["tenant_id"])
    req = CrossBorderRequest(
        user_id=UUID(body.user_id) if body.user_id else None,
        destination_country=body.destination_country,
        destination_entity=body.destination_entity,
        data_categories=body.data_categories,
        legal_basis=body.legal_basis,
        legal_basis_ref=body.legal_basis_ref,
    )
    try:
        transfer = await request_cross_border_transfer(
            session, tenant_id=tenant_id, request=req
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return CrossBorderResponse(
        transfer_id=str(transfer.transfer_id),
        destination_country=transfer.destination_country,
        destination_entity=transfer.destination_entity,
        legal_basis=transfer.legal_basis,
        approved=transfer.approved,
        approver_id=None,
        approved_at=None,
    )


@router.patch("/cross-border/{transfer_id}/approve", summary="审批跨境传输")
async def approve_cross_border_endpoint(
    session: SessionDep,
    current: CurrentUserDep,
    transfer_id: str,
    body: CrossBorderApproveRequest = Body(...),
) -> CrossBorderResponse:
    """DPA 审批跨境传输."""
    tid = UUID(transfer_id)
    approver = _actor_id(current)
    transfer = await approve_cross_border_transfer(
        session,
        transfer_id=tid,
        approver_id=approver,
        approved=body.approved,
        notes=body.notes,
    )
    if transfer is None:
        raise HTTPException(status_code=404, detail="传输记录不存在")
    return CrossBorderResponse(
        transfer_id=str(transfer.transfer_id),
        destination_country=transfer.destination_country,
        destination_entity=transfer.destination_entity,
        legal_basis=transfer.legal_basis,
        approved=transfer.approved,
        approver_id=str(transfer.approver_id) if transfer.approver_id else None,
        approved_at=transfer.approved_at,
    )


# ===== 隐私政策 =====


@router.get("/privacy-policy", summary="当前隐私政策")
async def get_privacy_policy(_: CurrentUserDep) -> PrivacyPolicyResponse:
    """Phase 5 B26 — 返回当前生效的隐私政策."""
    from datetime import datetime

    return PrivacyPolicyResponse(
        version=CURRENT_POLICY_VERSION,
        title="HSCredit Studio 隐私政策",
        content=PRIVACY_POLICY_ZH,
        published_at=datetime.now(UTC),
        is_current=True,
    )


@router.get("/legal-basis", summary="跨境传输法律基础列表")
async def get_legal_basis(_: CurrentUserDep) -> dict[str, Any]:
    """列出 PIPL 第 38 条规定的 4 种法律基础."""
    return {"bases": list(CROSS_BORDER_BASIS_VALUES), "pipl_article": "38"}


__all__ = ["router"]
