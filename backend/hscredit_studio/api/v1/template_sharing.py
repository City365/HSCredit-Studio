"""模板共享 API — Phase 6 B31.

依据 docs/ROADMAP.md Phase 6 B31:

| 端点 | 方法 | 用途 |
|---|---|---|
| /template-sharing/publish | POST | 从工作流发布为租户模板 (B31 验收) |
| /template-sharing/{template_id}/share | POST | 申请跨租户共享 (draft → pending) |
| /template-sharing/{template_id}/review | POST | 审核 (super_admin / tenant_admin) |
| /template-sharing/{template_id}/logs | GET | 审核日志 |
"""
from __future__ import annotations

from uuid import UUID
from uuid import UUID as _UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from sqlalchemy import select

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep, require_permission, require_role
from hscredit_studio.models import TemplateReviewLog, WorkflowVersion
from hscredit_studio.schemas.template_sharing import (
    CrossTenantShareRequest,
    PublishedTemplateResponse,
    PublishWorkflowRequest,
    ReviewDecisionRequest,
    TemplateReviewLogItem,
    TemplateReviewLogList,
)
from hscredit_studio.services import template_sharing as svc
from hscredit_studio.services.rbac import Action, Resource, Role

router = APIRouter(tags=["模板共享"])


@router.post(
    "/publish",
    summary="从工作流发布为租户模板 (B31 验收)",
    response_model=PublishedTemplateResponse,
    dependencies=[Depends(require_permission(Resource.WORKFLOW, Action.WRITE))],
)
async def publish_workflow(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    body: PublishWorkflowRequest = Body(...),
) -> PublishedTemplateResponse:
    """从 Workflow 发布为租户内模板 (默认 draft 状态, 待审核)."""
    from sqlalchemy.exc import IntegrityError

    user_uuid = _UUID(user["sub"])
    try:
        tmpl = await svc.publish_workflow_as_template(
            session=session,
            tenant_id=_UUID(tenant_id),
            user_id=user_uuid,
            workflow_id=body.workflow_id,
            template_name=body.template_name,
            description=body.description,
            tags=body.tags,
            visibility=body.visibility,
        )
    except FeatureNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "E_NOT_FOUND", "message": str(e)},
        ) from e
    except IntegrityError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "E_CONFLICT", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "E_BAD_REQUEST", "message": str(e)},
        ) from e

    # 读取 v1 拓扑
    v1 = await session.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == body.workflow_id,
        ).order_by(WorkflowVersion.version_number.desc()).limit(1)
    )
    nodes = (v1.definition or {}).get("nodes", []) if v1 else []
    edges = (v1.definition or {}).get("edges", []) if v1 else []

    return PublishedTemplateResponse(
        template_id=tmpl.template_id,
        name=tmpl.name,
        visibility=tmpl.visibility,
        review_status=tmpl.review_status,
        source_workflow_id=tmpl.source_workflow_id,
        version_number=1,
        node_count=len(nodes),
        edge_count=len(edges),
        created_at=tmpl.created_at,
    )


@router.post(
    "/{template_id}/share",
    summary="申请跨租户共享 (B31)",
    response_model=PublishedTemplateResponse,
)
async def request_share(
    session: SessionDep,
    user: CurrentUserDep,
    template_id: UUID = Path(...),
    body: CrossTenantShareRequest = Body(...),
) -> PublishedTemplateResponse:
    """申请将模板共享给其他租户 (draft/rejected → pending)."""
    user_uuid = _UUID(user["sub"])
    try:
        tmpl = await svc.request_cross_tenant_share(
            session=session,
            template_id=template_id,
            requester_id=user_uuid,
            target_tenants=body.target_tenants,
            reason=body.reason,
        )
    except Exception as e:
        if isinstance(e, FeatureNotFoundError):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "E_NOT_FOUND", "message": str(e)},
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "E_BAD_REQUEST", "message": str(e)},
        ) from e

    return PublishedTemplateResponse(
        template_id=tmpl.template_id,
        name=tmpl.name,
        visibility=tmpl.visibility,
        review_status=tmpl.review_status,
        source_workflow_id=tmpl.source_workflow_id,
        version_number=1,
        node_count=0,
        edge_count=0,
        created_at=tmpl.created_at,
    )


@router.post(
    "/{template_id}/review",
    summary="审核模板 (B31)",
    response_model=PublishedTemplateResponse,
    dependencies=[Depends(require_role(Role.TENANT_ADMIN))],
)
async def review_template_endpoint(
    session: SessionDep,
    user: CurrentUserDep,
    template_id: UUID = Path(...),
    body: ReviewDecisionRequest = Body(...),
) -> PublishedTemplateResponse:
    """审核 (通过/拒绝) 模板的跨租户共享申请. tenant_admin 权限."""
    user_uuid = _UUID(user["sub"])
    try:
        tmpl = await svc.review_template(
            session=session,
            template_id=template_id,
            reviewer_id=user_uuid,
            approve=body.approve,
            rejection_reason=body.rejection_reason,
            comment=body.comment,
            granted_tenants=body.granted_tenants,
        )
    except Exception as e:
        if isinstance(e, FeatureNotFoundError):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "E_NOT_FOUND", "message": str(e)},
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "E_BAD_REQUEST", "message": str(e)},
        ) from e

    return PublishedTemplateResponse(
        template_id=tmpl.template_id,
        name=tmpl.name,
        visibility=tmpl.visibility,
        review_status=tmpl.review_status,
        source_workflow_id=tmpl.source_workflow_id,
        version_number=1,
        node_count=0,
        edge_count=0,
        created_at=tmpl.created_at,
    )


@router.get(
    "/{template_id}/logs",
    summary="模板审核日志 (B31)",
    response_model=TemplateReviewLogList,
)
async def list_review_logs(
    session: SessionDep,
    _: CurrentUserDep,
    template_id: UUID = Path(...),
) -> TemplateReviewLogList:
    """列出指定模板的审核历史."""
    rows = (
        await session.execute(
            select(TemplateReviewLog)
            .where(TemplateReviewLog.template_id == template_id)
            .order_by(TemplateReviewLog.created_at.desc())
        )
    ).scalars().all()
    items = [
        TemplateReviewLogItem(
            log_id=r.log_id,
            template_id=r.template_id,
            reviewer_id=r.reviewer_id,
            old_status=r.old_status,
            new_status=r.new_status,
            comment=r.comment,
            extra=r.extra,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return TemplateReviewLogList(items=items, total=len(items))


from hscredit_studio.core.exceptions import FeatureNotFoundError  # noqa: E402

__all__ = ["router"]
