"""行业模板市场服务 — Phase 6 B30.

依据 docs/ROADMAP.md Phase 6 B30:

- 6 个内置行业模板 (银行信用卡/消金/助贷/现金贷/电商分期/汽车金融)
- 模板预览 (只读): 含 nodes/edges + 推荐特征 + 评分公式
- 一键实例化: 由 ``instantiate_template`` 完成 (services/template.py)
- 评分: 复用现有 TemplateRating

本模块:
- :func:`list_industry_templates` — 模板市场列表 (B30 验收: 含 6 个行业模板)
- :func:`get_industry_template_detail` — 模板预览 (含完整 topology)
- :func:`instantiate_industry_template` — 一键实例化 (包装 instantiate_template)
- :func:`rate_industry_template` — 模板评分 (复用 rate_template)
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.models import Template
from hscredit_studio.services.industry_templates import INDUSTRY_TEMPLATES
from hscredit_studio.services.template import (
    get_latest_version,
    get_template,
    instantiate_template,
    rate_template,
)

INDUSTRY_NAMES: set[str] = {t["industry"] for t in INDUSTRY_TEMPLATES}
"""6 个行业名称集合, 用于识别行业模板 (区别于平台通用模板)."""


async def list_industry_templates(
    session: AsyncSession,
    *,
    search: str | None = None,
    industry: str | None = None,
) -> tuple[list[Template], int]:
    """列出所有行业模板 (B30 模板市场).

    行业模板通过 ``tags`` 字段包含 ``industry`` 标记, 或通过 ``industry`` 元数据
    (存储在 ``description`` 或 ``tags`` 中) 识别. 本实现使用 ``tags`` 第一个元素
    与 ``INDUSTRY_NAMES`` 比对.

    Returns:
        (templates, total)
    """
    stmt = select(Template).where(
        Template.tenant_id.is_(None),
        Template.deleted_at.is_(None),
        Template.visibility == "public",
    )
    if industry:
        stmt = stmt.where(Template.tags.contains([industry]))

    rows = (await session.execute(stmt.order_by(Template.use_count.desc()))).scalars().all()

    if search:
        kw = search.lower()
        rows = [t for t in rows if kw in (t.name or "").lower() or kw in (t.description or "").lower()]

    # 过滤出含行业标记的 (兼容老平台模板不带 industry tag)
    industry_tagged = [t for t in rows if any(tag in INDUSTRY_NAMES for tag in (t.tags or []))]

    return industry_tagged, len(industry_tagged)


async def get_industry_template_detail(
    session: AsyncSession,
    template_id: UUID,
) -> dict[str, Any]:
    """返回行业模板的完整详情 (B30 预览).

    通过 :func:`get_template` (RLS-safe) 获取 Template, 再通过 :func:`get_latest_version`
    读取 nodes/edges/default_params.

    Returns:
        字典包含完整元数据 + topology.

    Raises:
        FeatureNotFoundError: 模板不存在.
    """
    tmpl = await get_template(session, tenant_id=UUID(int=0), template_id=template_id)
    version = await get_latest_version(session, template_id)

    # 解析 industry (从 tags 中找)
    industry = "通用"
    for tag in tmpl.tags or []:
        if tag in INDUSTRY_NAMES:
            industry = tag
            break

    # 推荐特征 + 评分公式 + 报告模板 (从 default_params 取, 否则从 description)
    default_params = version.default_params or {}

    return {
        "template_id": str(tmpl.template_id),
        "name": tmpl.name,
        "industry": industry,
        "category": tmpl.category,
        "description": tmpl.description,
        "icon": tmpl.icon,
        "tags": list(tmpl.tags or []),
        "target_column": default_params.get("target_column", "FPD"),
        "recommended_features": list(default_params.get("recommended_features", [])),
        "model_type": default_params.get("model_type", "逻辑回归 + WOE"),
        "score_formula": default_params.get("score_formula", ""),
        "report_template": default_params.get("report_template", ""),
        "default_dataset": default_params.get("default_dataset", "examples/hscredit_yyp.xlsx"),
        "nodes": list(version.nodes or []),
        "edges": list(version.edges or []),
        "version_number": version.version_number,
        "use_count": tmpl.use_count,
    }


async def instantiate_industry_template(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    template_id: UUID,
    workflow_name: str | None = None,
    params_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """一键实例化行业模板 (B30 验收).

    包装 ``instantiate_template``, 完成后返回完整结构 (含 topology 摘要).
    """
    from sqlalchemy import select

    from hscredit_studio.models import WorkflowVersion

    wf = await instantiate_template(
        session=session,
        tenant_id=tenant_id,
        user_id=user_id,
        template_id=template_id,
        workflow_name=workflow_name,
        params_overrides=params_overrides,
    )

    # 直接 query 版本避免 lazy-load (greenlet)
    v1 = await session.scalar(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == wf.workflow_id)
        .order_by(WorkflowVersion.version_number.asc())
        .limit(1)
    )
    definition = (v1.definition or {}) if v1 else {}
    nodes = list(definition.get("nodes", []))
    edges = list(definition.get("edges", []))

    return {
        "template_id": str(template_id),
        "template_name": wf.description.replace("从模板「", "").replace("」实例化", "") if wf.description else "",
        "workflow_id": str(wf.workflow_id),
        "workflow_name": wf.name,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "created_at": wf.created_at.isoformat(),
    }


async def rate_industry_template(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    template_id: UUID,
    rating: int,
    comment: str | None = None,
) -> dict[str, Any]:
    """给行业模板评分 (B30).

    复用现有 :func:`rate_template`. 返回新 rating_id + 最新 rating_avg/count.
    """
    rating_row = await rate_template(
        session=session,
        tenant_id=tenant_id,
        user_id=user_id,
        template_id=template_id,
        rating=rating,
        comment=comment,
    )
    tmpl = await session.get(Template, template_id)
    return {
        "template_id": str(template_id),
        "rating_id": str(rating_row.rating_id),
        "rating": rating_row.rating,
        "rating_avg": float(tmpl.rating_avg) if tmpl.rating_avg is not None else None,
        "rating_count": tmpl.rating_count,
    }


__all__ = [
    "INDUSTRY_NAMES",
    "get_industry_template_detail",
    "instantiate_industry_template",
    "list_industry_templates",
    "rate_industry_template",
]
