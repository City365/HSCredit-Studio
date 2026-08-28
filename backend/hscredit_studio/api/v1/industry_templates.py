"""行业模板市场 API — Phase 6 B30.

依据 docs/ROADMAP.md Phase 6 B30:

| 端点 | 方法 | 用途 |
|---|---|---|
| /industry-templates | GET | 模板市场列表 (6 个行业模板) |
| /industry-templates/{id} | GET | 模板详情 (只读预览) |
| /industry-templates/{id}/instantiate | POST | 一键实例化 |
| /industry-templates/{id}/rate | POST | 评分 (1-5 星) |
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep, require_permission
from hscredit_studio.schemas.industry_templates import (
    IndustryTemplateDetail,
    IndustryTemplateInstantiateRequest,
    IndustryTemplateInstantiateResponse,
    IndustryTemplateListResponse,
    IndustryTemplateRatingCreate,
    IndustryTemplateRatingResponse,
    IndustryTemplateSummary,
)
from hscredit_studio.services import industry_marketplace as svc
from hscredit_studio.services.rbac import Action, Resource

router = APIRouter(tags=["模板市场"])


@router.get(
    "",
    summary="行业模板市场列表 (B30 验收)",
    response_model=IndustryTemplateListResponse,
)
async def list_industry_templates(
    session: SessionDep,
    _: CurrentUserDep,
    search: str | None = Query(None),
    industry: str | None = Query(None, description="行业过滤: 银行信用卡 / 互联网消金 / 助贷 / 现金贷 / 电商分期 / 汽车金融"),
) -> IndustryTemplateListResponse:
    """模板市场列表 — 6 个内置行业模板."""
    templates, total = await svc.list_industry_templates(
        session, search=search, industry=industry,
    )
    items = []
    for t in templates:
        # industry 由 tags 推导
        industry_name = "通用"
        for tag in (t.tags or []):
            if tag in svc.INDUSTRY_NAMES:
                industry_name = tag
                break
        # 节点/边数: 从 latest version 取
        from hscredit_studio.services.template import get_latest_version

        try:
            v = await get_latest_version(session, t.template_id)
            nc = len(v.nodes or [])
            ec = len(v.edges or [])
            dp = v.default_params or {}
        except Exception:
            nc = ec = 0
            dp = {}

        items.append(
            IndustryTemplateSummary(
                template_id=t.template_id,
                name=t.name,
                industry=industry_name,
                category=t.category,
                description=t.description,
                icon=t.icon,
                tags=list(t.tags or []),
                target_column=dp.get("target_column", "FPD"),
                model_type=dp.get("model_type", ""),
                score_formula=dp.get("score_formula", ""),
                node_count=nc,
                edge_count=ec,
                recommended_features=list(dp.get("recommended_features", [])),
                use_count=t.use_count,
                rating_avg=float(t.rating_avg) if t.rating_avg is not None else None,
                rating_count=t.rating_count,
            )
        )

    return IndustryTemplateListResponse(items=items, total=total)


@router.get(
    "/{template_id}",
    summary="行业模板详情 (只读预览)",
    response_model=IndustryTemplateDetail,
)
async def get_industry_template_detail(
    session: SessionDep,
    _: CurrentUserDep,
    template_id: UUID = Path(...),
) -> IndustryTemplateDetail:
    """返回完整模板详情 + 元数据 + 节点拓扑."""
    try:
        d = await svc.get_industry_template_detail(session, template_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "E_NOT_FOUND", "message": str(e)},
        ) from e
    return IndustryTemplateDetail(**d)


@router.post(
    "/{template_id}/instantiate",
    summary="一键实例化 (B30 验收)",
    response_model=IndustryTemplateInstantiateResponse,
    dependencies=[Depends(require_permission(Resource.WORKFLOW, Action.WRITE))],
)
async def instantiate_industry_template(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    template_id: UUID = Path(...),
    body: IndustryTemplateInstantiateRequest = Body(...),
) -> IndustryTemplateInstantiateResponse:
    """一键从行业模板生成工作流 (B30 验收: 银行信用卡 → 8+ 节点工作流)."""
    from uuid import UUID as _UUID

    user_uuid = _UUID(user["sub"])
    result = await svc.instantiate_industry_template(
        session=session,
        tenant_id=_UUID(tenant_id),
        user_id=user_uuid,
        template_id=template_id,
        workflow_name=body.workflow_name,
        params_overrides=body.params_overrides or None,
    )
    return IndustryTemplateInstantiateResponse(**result)


@router.post(
    "/{template_id}/rate",
    summary="模板评分 (B30)",
    response_model=IndustryTemplateRatingResponse,
)
async def rate_industry_template(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    template_id: UUID = Path(...),
    body: IndustryTemplateRatingCreate = Body(...),
) -> IndustryTemplateRatingResponse:
    """给行业模板 1-5 星评分 (B30)."""
    from uuid import UUID as _UUID

    user_uuid = _UUID(user["sub"])
    result = await svc.rate_industry_template(
        session=session,
        tenant_id=_UUID(tenant_id),
        user_id=user_uuid,
        template_id=template_id,
        rating=body.rating,
        comment=body.comment,
    )
    return IndustryTemplateRatingResponse(**result)


__all__ = ["router"]
