"""合同 API — Phase 4 B21.

依据 docs/ROADMAP.md Phase 4 B21:

- ``POST /api/v1/{tenant}/contracts`` — 申请合同 (service_agreement / dpa / nda / quote)
- ``GET  /api/v1/{tenant}/contracts`` — 列出合同
- ``GET  /api/v1/{tenant}/contracts/{id}`` — 合同详情
- ``POST /api/v1/{tenant}/contracts/{id}/sign`` — 签约 (mock e签章)
- ``POST /api/v1/{tenant}/bills/{bill_id}/vat-invoice`` — 申请增值税专票
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Query
from sqlalchemy import select

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep
from hscredit_studio.models import Contract, Tenant
from hscredit_studio.services.contracts import (
    CONTRACT_TEMPLATES,
    generate_contract_for_tenant,
    sign_contract,
)
from hscredit_studio.services.vat_invoice import (
    VatInvoiceApplication,
    submit_vat_invoice_application,
)

router = APIRouter(tags=["合同"])


@router.get(
    "/templates",
    summary="合同模板列表",
)
async def list_templates() -> dict[str, Any]:
    """Phase 4 B21 — 列出可用合同模板."""
    return {
        "templates": [
            {
                "contract_type": ct,
                "title_template": t["title_template"],
                "validity_months": t["validity_months"],
                "sections_count": len(t["sections"]),
            }
            for ct, t in CONTRACT_TEMPLATES.items()
        ],
    }


@router.get(
    "",
    summary="租户合同列表",
)
async def list_contracts(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """列出租户合同."""
    tid = UUID(tenant_id)
    contracts = (
        await session.execute(
            select(Contract)
            .where(Contract.tenant_id == tid)
            .order_by(Contract.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "contract_id": str(c.contract_id),
                "contract_number": c.contract_number,
                "contract_type": c.contract_type,
                "title": c.title,
                "status": c.status,
                "valid_from": c.valid_from.isoformat() if c.valid_from else None,
                "valid_until": c.valid_until.isoformat() if c.valid_until else None,
                "signed_at": c.signed_at.isoformat() if c.signed_at else None,
                "pdf_path": c.pdf_path,
            }
            for c in contracts
        ],
        "count": len(contracts),
    }


@router.post(
    "",
    summary="申请合同",
    description="生成合同草稿 (draft), 包含中文模板 + 电子签章占位",
)
async def create_contract(
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
    contract_type: str = Query(
        ...,
        pattern="^(service_agreement|dpa|nda|quote)$",
        description="合同类型",
    ),
) -> dict[str, Any]:
    """Phase 4 B21 — 生成合同."""
    tid = UUID(tenant_id)
    tenant = await session.scalar(select(Tenant).where(Tenant.tenant_id == tid))
    tenant_name = tenant.name if tenant else f"租户-{tid.hex[:8]}"
    contract = await generate_contract_for_tenant(tid, tenant_name, contract_type)
    return {
        "contract_id": str(contract.contract_id),
        "contract_number": contract.contract_number,
        "contract_type": contract.contract_type,
        "title": contract.title,
        "status": contract.status,
        "valid_from": contract.valid_from.isoformat() if contract.valid_from else None,
        "valid_until": contract.valid_until.isoformat() if contract.valid_until else None,
        "pdf_path": contract.pdf_path,
    }


@router.get(
    "/{contract_id}",
    summary="合同详情",
)
async def get_contract(
    contract_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
) -> dict[str, Any]:
    """Phase 4 B21 — 合同详情."""
    tid = UUID(tenant_id)
    c = await session.scalar(
        select(Contract).where(
            Contract.contract_id == contract_id,
            Contract.tenant_id == tid,
        )
    )
    if c is None:
        raise HTTPException(status_code=404, detail="合同不存在")
    return {
        "contract_id": str(c.contract_id),
        "contract_number": c.contract_number,
        "contract_type": c.contract_type,
        "title": c.title,
        "status": c.status,
        "valid_from": c.valid_from.isoformat() if c.valid_from else None,
        "valid_until": c.valid_until.isoformat() if c.valid_until else None,
        "signed_at": c.signed_at.isoformat() if c.signed_at else None,
        "pdf_path": c.pdf_path,
        "extra_metadata": c.extra_metadata,
    }


@router.post(
    "/{contract_id}/sign",
    summary="签约 (mock 电子签章)",
)
async def sign_contract_endpoint(
    contract_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
    _: CurrentUserDep,
) -> dict[str, Any]:
    """Phase 4 B21 — 签约合同."""
    tid = UUID(tenant_id)
    try:
        c = await sign_contract(contract_id, tid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "contract_id": str(c.contract_id),
        "contract_number": c.contract_number,
        "status": c.status,
        "signed_at": c.signed_at.isoformat() if c.signed_at else None,
    }


@router.post(
    "/vat-invoice/apply",
    summary="申请增值税专票",
    description="提交增值税专票 / 普票 / 收据申请, 含购买方税号校验",
)
async def apply_vat_invoice(
    tenant_id: TenantDep,
    _: CurrentUserDep,
    application: VatInvoiceApplication = Body(...),
) -> dict[str, Any]:
    """Phase 4 B21 — 增值税专票申请."""
    tid = UUID(tenant_id)
    try:
        invoice = await submit_vat_invoice_application(tid, application)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "invoice_id": str(invoice.invoice_id),
        "invoice_number": invoice.invoice_number,
        "invoice_type": invoice.invoice_type,
        "status": invoice.status,
        "buyer_name": invoice.buyer_name,
        "buyer_tax_id_prefix": invoice.buyer_tax_id[:6] + "***" if invoice.buyer_tax_id else None,
    }


__all__ = ["router"]
