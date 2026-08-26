"""节点定义 API — 供前端节点库动态加载.

依据 :file:`docs/design/03-node-catalog.md` 第 3.2 节，
节点定义由后端在启动时通过 NodeRegistry 同步到 ``node_definitions`` 表，
前端通过本端点拉取，不依赖硬编码。

路由前缀：``/api/v1/{tenant_slug}/node-definitions``（见 ``main.py``）.
所有端点均需鉴权（``CurrentUserDep``）+ 租户隔离（``TenantDep``）.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import select

from hscredit_studio.api.deps import CurrentUserDep, SessionDep, TenantDep
from hscredit_studio.models import NodeDefinition
from hscredit_studio.schemas.node_contract import (
    NodeContract,
    NodeDefinitionListResponse,
    NodeDefinitionResponse,
)

router = APIRouter(tags=["节点定义"])


@router.get(
    "",
    response_model=NodeDefinitionListResponse,
    summary="列出全部节点定义",
    description=(
        "返回 ``node_definitions`` 表中所有 ``enabled=true`` 的记录。"
        "支持按 ``category`` 过滤、按 ``search`` 模糊匹配 name/description。"
        "本端点数据由后端 ``NodeRegistry`` 在启动时同步；前端节点库"
        "应通过本端点加载，**禁止**硬编码节点列表。"
    ),
)
async def list_node_definitions(
    session: SessionDep,
    tenant_id: TenantDep,  # noqa: ARG001 — 触发租户校验
    user: CurrentUserDep,  # noqa: ARG001 — 仅用于鉴权
    category: str | None = Query(
        default=None,
        description="节点分类过滤（数据接入 / EDA / 特征工程 / 特征筛选 / 模型训练 / 评分卡与规则 / 报告与部署）",
    ),
    search: str | None = Query(
        default=None,
        max_length=128,
        description="模糊匹配节点中文名 / 描述 / node_type",
    ),
    enabled_only: bool = Query(
        default=True,
        description="是否仅返回启用节点（默认 true；管理员场景可置 false）",
    ),
    include_contract: bool = Query(
        default=True,
        description="是否包含完整 ``contract``（false 时仅返回元数据，用于轻量下拉框）",
    ),
    sort_by: Literal["node_type", "category", "name", "updated_at"] = Query(
        default="category",
        description="排序字段",
    ),
    sort_order: Literal["asc", "desc"] = Query(default="asc", description="排序方向"),
) -> NodeDefinitionListResponse:
    """列出节点定义.

    实现要点：

    - ``tenant_id`` 参数仅用于触发依赖注入链上的租户校验；``node_definitions``
      是系统级表，节点定义**全局共享**，不按租户过滤。
    - 当 ``include_contract=false`` 时，从响应中剥离 ``contract`` 字段以减少
      payload（节点库首页下拉场景可省 90%+ 体积）。
    - ``search`` 同时匹配 ``name`` / ``description`` / ``node_type``（大小写不敏感）。
    """
    stmt = select(NodeDefinition)
    if enabled_only:
        stmt = stmt.where(NodeDefinition.enabled.is_(True))
    if category:
        stmt = stmt.where(NodeDefinition.category == category)
    if search:
        like = f"%{search.lower()}%"
        # Postgres JSONB 描述字段用 ``.astext`` 提取文本后小写比较
        stmt = stmt.where(
            (NodeDefinition.name.ilike(like))
            | (NodeDefinition.description.ilike(like))
            | (NodeDefinition.node_type.ilike(like))
        )

    # 排序：category / node_type / name 是 ORM 列；updated_at 来自 TimestampMixin
    sort_col = {
        "node_type": NodeDefinition.node_type,
        "category": NodeDefinition.category,
        "name": NodeDefinition.name,
        "updated_at": NodeDefinition.updated_at,
    }[sort_by]
    stmt = stmt.order_by(sort_col.asc() if sort_order == "asc" else sort_col.desc())

    rows = (await session.scalars(stmt)).all()

    defs: list[NodeDefinitionResponse] = []
    for row in rows:
        contract_raw = row.contract or {}
        # contract_version: ORM 存 int；响应 schema 要求 str，做一次转换
        cv_int = row.contract_version or 1
        cv_str = (
            contract_raw.get("version")
            if isinstance(contract_raw, dict) and isinstance(contract_raw.get("version"), str)
            else f"{cv_int}.0.0"
        )
        if include_contract and contract_raw:
            contract_obj = NodeContract.model_validate(contract_raw)
        else:
            # 轻量模式：构造最小可用 stub（仅保留 NodeContract 必填字段）
            contract_obj = NodeContract(
                node_type=row.node_type,
                category=row.category,
                name=row.name,
            )
        defs.append(
            NodeDefinitionResponse(
                node_type=row.node_type,
                category=row.category,
                name=row.name,
                description=row.description or "",
                icon=row.icon or "📦",
                contract_version=cv_str,
                contract=contract_obj,
                enabled=row.enabled,
                is_custom=False,
            )
        )

    return NodeDefinitionListResponse(definitions=defs)


__all__ = ["router"]
