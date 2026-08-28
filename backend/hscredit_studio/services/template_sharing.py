"""自定义模板共享服务 — Phase 6 B31.

依据 docs/ROADMAP.md Phase 6 B31:

> 租户可将自定义工作流发布为租户内模板
> 跨租户模板市场 (可选, 治理复杂度高)
> 风险: 跨租户模板涉及 IP / 数据安全, 需先有模板审核流程

本模块实现:

- :func:`publish_workflow_as_template` — 从 Workflow 发布为租户模板
- :func:`request_cross_tenant_share` — 申请跨租户共享 (创建待审核记录)
- :func:`review_template` — 审核 (super_admin / tenant_admin)
- :func:`share_with_tenant` — 共享给指定租户 (审核通过后)
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.exceptions import FeatureNotFoundError, ValidationError
from hscredit_studio.models import (
    Template,
    TemplateReviewLog,
    TemplateVersion,
    Workflow,
    WorkflowVersion,
)

TEMPLATE_REVIEW_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending"},
    "pending": {"approved", "rejected", "draft"},
    "approved": {"pending"},  # 重新申请可再走流程
    "rejected": {"draft"},  # 修订后回到 draft
}
"""模板审核状态机 (Phase 6 B31).

合法状态转换::

    draft → pending
    pending → approved | rejected | draft (撤回)
    approved → pending (重新申请)
    rejected → draft (修订)
"""


async def publish_workflow_as_template(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    workflow_id: UUID,
    template_name: str,
    description: str | None = None,
    tags: list[str] | None = None,
    visibility: str = "tenant",
) -> Template:
    """从 Workflow 发布为租户模板 (B31 验收).

    Args:
        tenant_id: 发起租户 (模板归属)
        user_id: 发布人
        workflow_id: 来源工作流
        template_name: 模板名
        description: 模板描述 (默认 = workflow.description)
        tags: 模板标签
        visibility: 可见性 (默认 tenant, 可选 private/public)

    Returns:
        新建的 Template ORM 对象, 含初始 v1 TemplateVersion (draft 状态).

    Raises:
        FeatureNotFoundError: 工作流不存在.
        ValidationError: 工作流没有任何版本 / 模板名重复.
    """
    if visibility not in ("private", "tenant", "public"):
        raise ValidationError(f"非法 visibility: {visibility}")

    wf = await session.get(Workflow, workflow_id)
    if wf is None or wf.tenant_id != tenant_id or wf.deleted_at is not None:
        raise FeatureNotFoundError(f"工作流 {workflow_id} 不存在或不属于当前租户")

    v1 = await session.scalar(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version_number.desc())
        .limit(1)
    )
    if v1 is None:
        raise ValidationError(f"工作流 {workflow_id} 没有任何版本")

    # 模板名唯一性: (tenant_id, name)
    existing = await session.scalar(
        select(Template).where(
            Template.tenant_id == tenant_id,
            Template.name == template_name,
        )
    )
    if existing is not None:
        raise ValidationError(f"租户内已存在同名模板: {template_name}")

    definition = v1.definition or {}
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    template = Template(
        tenant_id=tenant_id,
        category="评分卡",
        name=template_name,
        description=description or wf.description,
        visibility=visibility,
        tags=tags or [],
        icon=None,
        use_count=0,
        rating_avg=0.0,
        rating_count=0,
        created_by=user_id,
        review_status="draft",
        rejection_reason=None,
        shared_with_tenants=[],
        source_workflow_id=workflow_id,
    )
    session.add(template)
    await session.flush()

    version = TemplateVersion(
        template_id=template.template_id,
        version_number=1,
        nodes=nodes,
        edges=edges,
        default_params={
            "source_workflow_id": str(workflow_id),
            "published_by": str(user_id),
            "target_column": "FPD",
        },
        readme_md=f"# {template_name}\n\n{description or wf.description or ''}\n",
    )
    session.add(version)

    # 初始审核日志
    log = TemplateReviewLog(
        template_id=template.template_id,
        reviewer_id=user_id,
        old_status=None,
        new_status="draft",
        comment="从工作流发布",
        extra={"workflow_id": str(workflow_id)},
    )
    session.add(log)

    await session.commit()
    await session.refresh(template)
    return template


async def request_cross_tenant_share(
    session: AsyncSession,
    *,
    template_id: UUID,
    requester_id: UUID,
    target_tenants: list[UUID],
    reason: str | None = None,
) -> Template:
    """申请跨租户共享 (B31).

    将模板状态从 draft → pending, 并记录待审核日志.
    审核通过后 (super_admin 调用 :func:`approve_cross_tenant_share`)
    才真正写入 ``shared_with_tenants``.
    """
    if not target_tenants:
        raise ValidationError("target_tenants 不能为空")

    template = await session.get(Template, template_id)
    if template is None or template.deleted_at is not None:
        raise FeatureNotFoundError(f"模板 {template_id} 不存在")

    if template.review_status not in ("draft", "rejected"):
        raise ValidationError(
            f"模板当前状态 {template.review_status} 不允许申请共享 (仅 draft/rejected 可申请)"
        )

    old_status = template.review_status
    template.review_status = "pending"

    log = TemplateReviewLog(
        template_id=template_id,
        reviewer_id=requester_id,
        old_status=old_status,
        new_status="pending",
        comment=reason or "申请跨租户共享",
        extra={"target_tenants": [str(t) for t in target_tenants]},
    )
    session.add(log)
    await session.commit()
    await session.refresh(template)
    return template


async def review_template(
    session: AsyncSession,
    *,
    template_id: UUID,
    reviewer_id: UUID,
    approve: bool,
    rejection_reason: str | None = None,
    comment: str | None = None,
    granted_tenants: list[UUID] | None = None,
) -> Template:
    """审核模板 (B31).

    Args:
        approve: True = 通过, False = 拒绝.
        granted_tenants: 通过时写入 ``shared_with_tenants`` 的租户白名单.
        rejection_reason: 拒绝时记录原因.

    Raises:
        ValidationError: 当前状态不允许审核.
    """
    template = await session.get(Template, template_id)
    if template is None or template.deleted_at is not None:
        raise FeatureNotFoundError(f"模板 {template_id} 不存在")

    if template.review_status != "pending":
        raise ValidationError(
            f"模板当前状态 {template.review_status} 不允许审核 (仅 pending 可审核)"
        )

    new_status = "approved" if approve else "rejected"
    if new_status not in TEMPLATE_REVIEW_TRANSITIONS.get("pending", set()):
        raise ValidationError(f"非法状态转换: pending → {new_status}")

    template.review_status = new_status
    if approve:
        template.rejection_reason = None
        if granted_tenants:
            existing = list(template.shared_with_tenants or [])
            # 合并去重
            seen: set[str] = {str(t) for t in existing}
            for t in granted_tenants:
                key = str(t)
                if key not in seen:
                    existing.append(key)
                    seen.add(key)
            template.shared_with_tenants = existing
            # 通过 + 共享 → visibility 升级为 public
            template.visibility = "public"
    else:
        template.rejection_reason = rejection_reason or "审核拒绝"

    log = TemplateReviewLog(
        template_id=template_id,
        reviewer_id=reviewer_id,
        old_status="pending",
        new_status=new_status,
        comment=comment or rejection_reason,
        extra={
            "granted_tenants": [str(t) for t in (granted_tenants or [])],
        },
    )
    session.add(log)
    await session.commit()
    await session.refresh(template)
    return template


async def list_shared_templates_for_tenant(
    session: AsyncSession,
    tenant_id: UUID,
) -> list[Template]:
    """列出对当前租户可见的共享模板 (B31).

    可见条件:
    - tenant_id IS NULL (系统模板, 已在 list_industry_templates 处理)
    - tenant_id == 当前 (本租户私有)
    - tenant_id != 当前 AND 当前在 shared_with_tenants 中
    """
    from sqlalchemy import or_

    rows = (
        await session.execute(
            select(Template).where(
                Template.deleted_at.is_(None),
                Template.review_status == "approved",
                or_(
                    Template.tenant_id == tenant_id,
                    Template.shared_with_tenants.contains([str(tenant_id)]),
                ),
            )
        )
    ).scalars().all()
    return list(rows)


__all__ = [
    "TEMPLATE_REVIEW_TRANSITIONS",
    "list_shared_templates_for_tenant",
    "publish_workflow_as_template",
    "request_cross_tenant_share",
    "review_template",
]
