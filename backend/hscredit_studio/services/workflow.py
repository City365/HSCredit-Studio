"""工作流 CRUD + 版本管理服务.

提供：

- 工作流列表（分页 / 搜索 / tag 过滤 / 排序）
- 创建工作流（自动创建 v1 初始版本）
- 工作流详情（含当前版本定义 + 计数）
- PATCH 更新（字段变更 + definition 变更触发自动版本号递增）
- 软删除
- 版本管理（手动创建新版本、版本详情）
- 导入 / 导出（JSON 包形式）

设计要点（见 ``docs/design/14-api-specification.md`` 第 14.5 节）：

- 全部 ORM 查询均带 ``tenant_id`` 隔离 + ``deleted_at IS NULL`` 过滤。
- Definition 校验：节点 ID 唯一 + 边引用合法 + 无循环依赖。
- 版本号策略：每次 ``PATCH.definition`` / ``POST /versions`` 在 service
  层手动 +1（DB 唯一约束 ``(workflow_id, version_number)`` 兜底）。
- 导入复用 ``create_workflow`` 逻辑（保留原始 name + definition）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.exceptions import FeatureNotFoundError, ValidationError
from hscredit_studio.models import Run, Workflow, WorkflowVersion
from hscredit_studio.schemas.workflow import (
    WorkflowCreate,
    WorkflowDefinition,
    WorkflowExportResponse,
    WorkflowListItem,
    WorkflowResponse,
    WorkflowUpdate,
    WorkflowVersionCreate,
    WorkflowVersionResponse,
)


# ===== 列表 =====


async def list_workflows(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    tags: list[str] | None = None,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
) -> tuple[list[WorkflowListItem], int]:
    """分页列出工作流（按 tenant_id 隔离）. ``(items, total)``."""
    base = select(Workflow).where(
        Workflow.tenant_id == tenant_id,
        Workflow.deleted_at.is_(None),
    )
    count_q = select(func.count()).select_from(Workflow).where(
        Workflow.tenant_id == tenant_id,
        Workflow.deleted_at.is_(None),
    )

    # 搜索过滤：name / description 模糊匹配
    if search:
        search_filter = or_(
            Workflow.name.ilike(f"%{search}%"),
            Workflow.description.ilike(f"%{search}%"),
        )
        base = base.where(search_filter)
        count_q = count_q.where(search_filter)

    # tag 过滤：AND 语义（工作流必须包含所有 filter tags）
    # JSONB contains 操作符 ``@>`` 用于 PG 数组包含判断
    if tags:
        for tag in tags:
            base = base.where(Workflow.tags.contains([tag]))
            count_q = count_q.where(Workflow.tags.contains([tag]))

    # 排序（白名单字段由 ORM 决定，``getattr`` 兜底默认 ``updated_at``）
    sort_col = getattr(Workflow, sort_by, Workflow.updated_at)
    base = base.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())

    # 分页
    offset = (page - 1) * page_size
    base = base.offset(offset).limit(page_size)

    workflows = (await session.scalars(base)).all()
    total = (await session.scalar(count_q)) or 0

    # 转换为 ListItem — 附 last_run + current_version 信息
    items: list[WorkflowListItem] = []
    for wf in workflows:
        last_run = await session.scalar(
            select(Run)
            .where(Run.workflow_id == wf.workflow_id)
            .order_by(Run.submitted_at.desc())
            .limit(1)
        )

        current_version_number: int | None = None
        if wf.current_version_id is not None:
            current_v = await session.get(WorkflowVersion, wf.current_version_id)
            if current_v is not None:
                current_version_number = current_v.version_number

        items.append(
            WorkflowListItem(
                id=wf.workflow_id,
                name=wf.name,
                description=wf.description,
                tags=wf.tags or [],
                current_version_number=current_version_number,
                created_by=wf.created_by,
                created_at=wf.created_at,
                updated_at=wf.updated_at,
                last_run_at=last_run.submitted_at if last_run else None,
                last_run_status=last_run.status if last_run else None,
            )
        )

    return items, total


# ===== 创建 =====


async def create_workflow(
    session: AsyncSession,
    tenant_id: UUID,
    created_by: UUID,
    req: WorkflowCreate,
) -> WorkflowResponse:
    """创建工作流 + 初始版本 v1."""
    _validate_workflow_definition(req.definition)

    wf = Workflow(
        tenant_id=tenant_id,
        name=req.name,
        description=req.description,
        tags=req.tags or [],
        created_by=created_by,
        current_version_id=None,  # 创建版本后回填
    )
    session.add(wf)
    await session.flush()

    v1 = WorkflowVersion(
        workflow_id=wf.workflow_id,
        version_number=1,
        definition=req.definition.model_dump(mode="json"),
        change_summary="初始版本",
        created_by=created_by,
    )
    session.add(v1)
    await session.flush()

    wf.current_version_id = v1.version_id
    await session.commit()

    return await get_workflow(session, tenant_id, wf.workflow_id)


# ===== 详情 =====


async def get_workflow(
    session: AsyncSession,
    tenant_id: UUID,
    workflow_id: UUID,
) -> WorkflowResponse:
    """获取工作流详情（含当前版本定义 + 版本 / 执行计数）."""
    wf = await session.scalar(
        select(Workflow).where(
            Workflow.workflow_id == workflow_id,
            Workflow.tenant_id == tenant_id,
            Workflow.deleted_at.is_(None),
        )
    )
    if wf is None:
        raise FeatureNotFoundError(f"工作流 {workflow_id} 不存在")

    versions_count = (
        await session.scalar(
            select(func.count()).select_from(WorkflowVersion).where(
                WorkflowVersion.workflow_id == workflow_id,
            )
        )
        or 0
    )
    runs_count = (
        await session.scalar(
            select(func.count()).select_from(Run).where(Run.workflow_id == workflow_id)
        )
        or 0
    )

    current_version_number: int | None = None
    definition_dict: dict[str, Any] | None = None
    if wf.current_version_id is not None:
        current_v = await session.get(WorkflowVersion, wf.current_version_id)
        if current_v is not None:
            current_version_number = current_v.version_number
            definition_dict = current_v.definition

    # 最近一次 run（用于列表头部的"上次执行"信息）
    last_run = await session.scalar(
        select(Run)
        .where(Run.workflow_id == workflow_id)
        .order_by(Run.submitted_at.desc())
        .limit(1)
    )

    return WorkflowResponse(
        id=wf.workflow_id,
        name=wf.name,
        description=wf.description,
        tags=wf.tags or [],
        current_version_number=current_version_number,
        created_by=wf.created_by,
        created_at=wf.created_at,
        updated_at=wf.updated_at,
        last_run_at=last_run.submitted_at if last_run else None,
        last_run_status=last_run.status if last_run else None,
        definition=WorkflowDefinition(**definition_dict) if definition_dict else None,
        versions_count=versions_count,
        runs_count=runs_count,
    )


# ===== 更新 =====


async def update_workflow(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    workflow_id: UUID,
    req: WorkflowUpdate,
) -> WorkflowResponse:
    """更新工作流（PATCH 语义）— 若 ``definition`` 变更则自动创建新版本.

    Returns
    -------
    WorkflowResponse
        更新后的完整工作流详情。

    Raises
    ------
    FeatureNotFoundError
        工作流不存在或被软删除。
    ValidationError
        新 definition 存在循环 / 重复 ID / 边引用非法。
    """
    wf = await session.scalar(
        select(Workflow).where(
            Workflow.workflow_id == workflow_id,
            Workflow.tenant_id == tenant_id,
            Workflow.deleted_at.is_(None),
        )
    )
    if wf is None:
        raise FeatureNotFoundError(f"工作流 {workflow_id} 不存在")

    # 基础字段就地更新
    if req.name is not None:
        wf.name = req.name
    if req.description is not None:
        wf.description = req.description
    if req.tags is not None:
        wf.tags = req.tags

    # definition 变更 → 创建新版本（version_number +1）
    if req.definition is not None:
        _validate_workflow_definition(req.definition)

        latest_v = await session.scalar(
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == workflow_id)
            .order_by(WorkflowVersion.version_number.desc())
            .limit(1)
        )
        next_v_num = (latest_v.version_number + 1) if latest_v else 1

        new_version = WorkflowVersion(
            workflow_id=workflow_id,
            version_number=next_v_num,
            definition=req.definition.model_dump(mode="json"),
            change_summary=req.change_summary or f"更新到 v{next_v_num}",
            created_by=user_id,
        )
        session.add(new_version)
        await session.flush()

        wf.current_version_id = new_version.version_id

    wf.updated_at = datetime.utcnow()
    await session.commit()

    return await get_workflow(session, tenant_id, workflow_id)


# ===== 删除 =====


async def delete_workflow(
    session: AsyncSession,
    tenant_id: UUID,
    workflow_id: UUID,
) -> None:
    """软删除工作流（标记 ``deleted_at``）."""
    wf = await session.scalar(
        select(Workflow).where(
            Workflow.workflow_id == workflow_id,
            Workflow.tenant_id == tenant_id,
            Workflow.deleted_at.is_(None),
        )
    )
    if wf is None:
        raise FeatureNotFoundError(f"工作流 {workflow_id} 不存在")

    wf.deleted_at = datetime.utcnow()
    await session.commit()


# ===== 版本管理 =====


async def list_versions(
    session: AsyncSession,
    tenant_id: UUID,
    workflow_id: UUID,
) -> list[WorkflowVersionResponse]:
    """列出工作流的全部版本（按 version_number desc）."""
    wf = await session.get(Workflow, workflow_id)
    if wf is None or wf.tenant_id != tenant_id or wf.deleted_at is not None:
        raise FeatureNotFoundError(f"工作流 {workflow_id} 不存在")

    versions = (
        await session.scalars(
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == workflow_id)
            .order_by(WorkflowVersion.version_number.desc())
        )
    ).all()

    return [
        _to_version_response(v) for v in versions
    ]


async def create_version(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    workflow_id: UUID,
    req: WorkflowVersionCreate,
) -> WorkflowVersionResponse:
    """手动创建新版本（不通过 PATCH workflow，相当于直接打 tag）."""
    wf = await session.get(Workflow, workflow_id)
    if wf is None or wf.tenant_id != tenant_id or wf.deleted_at is not None:
        raise FeatureNotFoundError(f"工作流 {workflow_id} 不存在")

    _validate_workflow_definition(req.definition)

    latest_v = await session.scalar(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version_number.desc())
        .limit(1)
    )
    next_v_num = (latest_v.version_number + 1) if latest_v else 1

    new_v = WorkflowVersion(
        workflow_id=workflow_id,
        version_number=next_v_num,
        definition=req.definition.model_dump(mode="json"),
        change_summary=req.change_summary or f"手动创建 v{next_v_num}",
        created_by=user_id,
    )
    session.add(new_v)
    await session.flush()

    # 新版本自动成为 HEAD
    wf.current_version_id = new_v.version_id
    wf.updated_at = datetime.utcnow()
    await session.commit()

    return _to_version_response(new_v)


async def get_version(
    session: AsyncSession,
    tenant_id: UUID,
    workflow_id: UUID,
    version_number: int,
) -> WorkflowVersionResponse:
    """按 ``version_number`` 获取指定版本."""
    wf = await session.get(Workflow, workflow_id)
    if wf is None or wf.tenant_id != tenant_id or wf.deleted_at is not None:
        raise FeatureNotFoundError(f"工作流 {workflow_id} 不存在")

    v = await session.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow_id,
            WorkflowVersion.version_number == version_number,
        )
    )
    if v is None:
        raise FeatureNotFoundError(f"版本 v{version_number} 不存在")

    return _to_version_response(v)


# ===== 导入 / 导出 =====


async def export_workflow(
    session: AsyncSession,
    tenant_id: UUID,
    workflow_id: UUID,
) -> WorkflowExportResponse:
    """导出工作流为 JSON 包（workflow + latest_version + 导出元信息）.

    注：当前实现不含 run 记录（按 ``WorkflowExportResponse.runs`` 可选字段，
    Phase 1.5 接入复现功能时再展开）。
    """
    wf_resp = await get_workflow(session, tenant_id, workflow_id)
    versions = await list_versions(session, tenant_id, workflow_id)
    latest_version = versions[0] if versions else None
    if latest_version is None:
        raise FeatureNotFoundError(f"工作流 {workflow_id} 没有可导出的版本")

    return WorkflowExportResponse(
        workflow=wf_resp,
        latest_version=latest_version,
        runs=None,
        exported_at=datetime.utcnow(),
    )


async def import_workflow(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    payload: dict[str, Any],
) -> WorkflowResponse:
    """从 JSON 包导入工作流.

    复用 :func:`create_workflow` 路径（确保初始版本号 / 校验 / 回填逻辑一致）。
    ``payload`` 形如 ``{"workflow": {...}, "latest_version": {...}}``。
    """
    wf_data = payload.get("workflow") or {}
    ver_data = payload.get("latest_version") or {}
    if not wf_data or not ver_data:
        raise ValidationError("导入包格式错误：缺少 workflow 或 latest_version")

    create_req = WorkflowCreate(
        name=wf_data.get("name", "Imported Workflow"),
        description=wf_data.get("description"),
        tags=wf_data.get("tags", []) or [],
        definition=WorkflowDefinition(**ver_data["definition"]),
    )
    return await create_workflow(session, tenant_id, user_id, create_req)


# ===== 内部辅助 =====


def _to_version_response(v: WorkflowVersion) -> WorkflowVersionResponse:
    """ORM WorkflowVersion → WorkflowVersionResponse."""
    return WorkflowVersionResponse(
        id=v.version_id,
        workflow_id=v.workflow_id,
        version_number=v.version_number,
        definition=WorkflowDefinition(**v.definition),
        change_summary=v.change_summary,
        created_by=v.created_by,
        created_at=v.created_at,
        updated_at=v.created_at,
    )


def _validate_workflow_definition(definition: WorkflowDefinition) -> None:
    """校验 workflow 定义合理性.

    - 节点 ID 在同一 workflow 内唯一。
    - 边的 ``source`` / ``target`` 必须引用已声明的节点。
    - 无循环依赖（DFS 三色染色检测）。

    Raises
    ------
    ValidationError
        任一校验失败。
    """
    node_ids = [n.id for n in definition.nodes]
    if len(node_ids) != len(set(node_ids)):
        dup_ids = sorted({nid for nid in node_ids if node_ids.count(nid) > 1})
        raise ValidationError(
            f"节点 ID 必须唯一，重复节点: {', '.join(dup_ids)}",
            details={"duplicate_node_ids": dup_ids},
        )

    node_id_set = set(node_ids)
    for edge in definition.edges:
        if edge.source not in node_id_set:
            raise ValidationError(
                f"边引用了不存在的源节点 {edge.source}",
                details={"edge_source": edge.source, "edge_target": edge.target},
            )
        if edge.target not in node_id_set:
            raise ValidationError(
                f"边引用了不存在的目标节点 {edge.target}",
                details={"edge_source": edge.source, "edge_target": edge.target},
            )

    if _has_cycle(definition.nodes, definition.edges):
        raise ValidationError("工作流包含循环依赖")


def _has_cycle(nodes: list, edges: list) -> bool:
    """DFS 三色染色检测有向图循环."""
    adj: dict[str, list[str]] = {n.id: [] for n in nodes}
    for e in edges:
        adj[e.source].append(e.target)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n.id: WHITE for n in nodes}

    def dfs(u: str) -> bool:
        color[u] = GRAY
        for v in adj[u]:
            cv = color.get(v, WHITE)
            if cv == GRAY:
                return True
            if cv == WHITE and dfs(v):
                return True
        color[u] = BLACK
        return False

    return any(color[n.id] == WHITE and dfs(n.id) for n in nodes)


__all__ = [
    "list_workflows",
    "create_workflow",
    "get_workflow",
    "update_workflow",
    "delete_workflow",
    "list_versions",
    "create_version",
    "get_version",
    "export_workflow",
    "import_workflow",
]