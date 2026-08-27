"""模板 API 路由 — 列表 / 详情 / 实例化 / 评分.

路由前缀：``/api/v1/{tenant_slug}/templates``（见 :mod:`hscredit_studio.main`）。

端点清单（与 docs/design/14-api-specification.md 第 14.7.4 节对齐）：

- ``GET    /templates``                              — 模板列表（系统 + 租户）
- ``GET    /templates/{template_id}``                 — 模板详情
- ``POST   /templates/{template_id}/instantiate``     — 从模板实例化工作流
- ``POST   /templates/{template_id}/ratings``         — 提交 / 更新评分

所有端点均需鉴权（``CurrentUserDep``）+ 租户隔离（``TenantDep``）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep
from hscredit_studio.models import Template
from hscredit_studio.schemas.common import PaginatedResponse
from hscredit_studio.schemas.workflow import WorkflowResponse
from hscredit_studio.services import template as tmpl_service
from hscredit_studio.services import workflow as wf_service

router = APIRouter(tags=["模板"])


# ===== Pydantic 模型 =====


class TemplateListItem(BaseModel):
    """模板列表项 — UI 卡片网格用."""

    id: UUID = Field(..., description="模板 UUID")
    name: str = Field(..., description="模板名")
    description: str | None = Field(default=None, description="模板描述")
    category: str = Field(..., description="模板分类")
    icon: str | None = Field(default=None, description="显示图标（emoji）")
    tags: list[str] = Field(default_factory=list, description="标签数组")
    visibility: str = Field(..., description="可见性（private / tenant / public）")
    use_count: int = Field(default=0, ge=0, description="被实例化次数")
    rating_avg: float = Field(default=0.0, ge=0.0, le=5.0, description="平均评分")
    rating_count: int = Field(default=0, ge=0, description="评分人数")
    is_system: bool = Field(default=False, description="是否系统模板（tenant_id IS NULL）")

    @classmethod
    def from_orm(cls, t: Template) -> TemplateListItem:
        return cls(
            id=t.template_id,
            name=t.name,
            description=t.description,
            category=t.category,
            icon=t.icon,
            tags=t.tags or [],
            visibility=t.visibility,
            use_count=t.use_count or 0,
            rating_avg=float(t.rating_avg) if t.rating_avg is not None else 0.0,
            rating_count=t.rating_count or 0,
            is_system=(t.tenant_id is None),
        )


class TemplateInstantiateRequest(BaseModel):
    """实例化模板请求体."""

    workflow_name: str | None = Field(
        default=None,
        max_length=200,
        description="新工作流名（不指定则用模板名 + 时间戳）",
    )
    params_overrides: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="节点参数覆盖 {node_id: {param: value}}",
    )


class TemplateRateRequest(BaseModel):
    """模板评分请求体."""

    rating: int = Field(..., ge=1, le=5, description="评分（1-5 整数）")
    comment: str | None = Field(default=None, max_length=500, description="评论")


class TemplateRateResponse(BaseModel):
    """模板评分响应."""

    rating_id: UUID = Field(..., description="评分记录 ID")
    rating: int = Field(..., description="评分值")


# ===== 路由 =====


@router.get(
    "",
    response_model=PaginatedResponse[TemplateListItem],
    summary="模板列表",
    description=(
        "分页列出当前租户可见的模板 — 包含系统模板（tenant_id IS NULL）"
        "与当前租户私有模板。支持按 category / search 过滤。"
    ),
)
async def list_templates(
    session: SessionDep,
    tenant_id: TenantDep,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=200, description="每页条数"),
    search: str | None = Query(default=None, description="模糊匹配 name / description"),
    category: str | None = Query(default=None, description="模板分类"),
) -> PaginatedResponse[TemplateListItem]:
    items, total = await tmpl_service.list_templates(
        session,
        UUID(tenant_id),
        page=page,
        page_size=page_size,
        search=search,
        category=category,
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return PaginatedResponse[TemplateListItem](
        items=[TemplateListItem.from_orm(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{template_id}",
    response_model=TemplateListItem,
    summary="模板详情",
    description="获取模板详情（系统模板或当前租户模板可访问）",
)
async def get_template(
    template_id: UUID,
    session: SessionDep,
    tenant_id: TenantDep,
) -> TemplateListItem:
    t = await tmpl_service.get_template(session, UUID(tenant_id), template_id)
    return TemplateListItem.from_orm(t)


@router.post(
    "/{template_id}/instantiate",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="从模板实例化工作流",
    description=(
        "基于模板最新版本创建一个新工作流 + 初始 WorkflowVersion。"
        "可通过 params_overrides 覆盖特定节点参数（如指定 CSV 路径）。"
    ),
)
async def instantiate_template(
    template_id: UUID,
    req: TemplateInstantiateRequest,
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
) -> WorkflowResponse:
    user_id = UUID(user["sub"])
    wf = await tmpl_service.instantiate_template(
        session,
        UUID(tenant_id),
        user_id,
        template_id,
        workflow_name=req.workflow_name,
        params_overrides=req.params_overrides,
    )
    return await wf_service.get_workflow(session, UUID(tenant_id), wf.workflow_id)


@router.post(
    "/{template_id}/ratings",
    response_model=TemplateRateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="为模板评分",
    description=(
        "提交或更新对模板的评分（1-5 整数），可附评论。" "同一用户对同一模板限唯一评分；提交后自动重算模板平均分。"
    ),
)
async def rate_template(
    template_id: UUID,
    req: TemplateRateRequest,
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
) -> TemplateRateResponse:
    user_id = UUID(user["sub"])
    r = await tmpl_service.rate_template(
        session,
        UUID(tenant_id),
        user_id,
        template_id,
        req.rating,
        req.comment,
    )
    return TemplateRateResponse(rating_id=r.rating_id, rating=r.rating)


__all__ = ["router"]
