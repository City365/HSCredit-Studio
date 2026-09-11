"""节点定义 API — 供前端节点库动态加载.

依据 :file:`docs/design/03-node-catalog.md` 第 3.2 节，
节点定义由后端在启动时通过 NodeRegistry 同步到 ``node_definitions`` 表，
前端通过本端点拉取，不依赖硬编码。

路由前缀：``/api/v1/{tenant_slug}/node-definitions``（见 ``main.py``）.
所有端点均需鉴权（``CurrentUserDep``）+ 租户隔离（``TenantDep``）.

Phase 6 B36 节点管理扩展:
- GET /{node_type} — 单节点详情
- PUT /{node_type}/enable — 启用 (super_admin)
- PUT /{node_type}/disable — 停用 (super_admin)
- PUT /{node_type}/meta — 改 name/description/icon (super_admin)
- POST /sync — 从 NodeRegistry 重新同步系统节点 (super_admin)

路由顺序很重要! FastAPI 按声明顺序匹配, /sync 和 /{node_type}/* 具体子路径必须
放在 /{node_type} catch-all 之前, 否则会被 /{node_type} 截胡.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from hscredit_studio.api.deps import (
    CurrentUserDep,
    SessionDep,
    TenantDep,
    require_role,
)
from hscredit_studio.core.logging import get_logger
from hscredit_studio.models import NodeDefinition
from hscredit_studio.nodes import NodeRegistry
from hscredit_studio.schemas.node_contract import (
    NodeContract,
    NodeDefinitionListResponse,
    NodeDefinitionResponse,
)
from hscredit_studio.services.audit import record_event
from hscredit_studio.services.rbac import Role

_log = get_logger(__name__)
router = APIRouter(tags=["节点定义"])


# ===== Schemas =====


class NodeMetaUpdateRequest(BaseModel):
    """节点元数据更新请求."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=32)


class NodeToggleResponse(BaseModel):
    """启用/停用响应."""

    node_type: str
    enabled: bool
    updated_at: str  # ISO 8601


class SyncResultResponse(BaseModel):
    """同步结果."""

    synced: int
    added: int
    updated: int
    removed: int


# ===== 辅助函数 =====


async def _get_node_definition_or_404(
    session, node_type: str
) -> NodeDefinition:
    """按 node_type 取节点定义, 不存在抛 404."""
    nd = await session.get(NodeDefinition, node_type)
    if nd is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "E_NODE_NOT_FOUND",
                "message": f"节点类型 {node_type} 不存在",
                "node_type": node_type,
            },
        )
    return nd


def _to_node_definition_response(row: NodeDefinition) -> NodeDefinitionResponse:
    """ORM 行 → API 响应 (含 contract 重建)."""
    contract_raw = row.contract or {}
    cv_int = row.contract_version or 1
    cv_str = (
        contract_raw.get("version")
        if isinstance(contract_raw, dict) and isinstance(contract_raw.get("version"), str)
        else f"{cv_int}_{id(row)}"
    )
    if contract_raw:
        contract_obj = NodeContract.model_validate(contract_raw)
    else:
        contract_obj = NodeContract(
            node_type=row.node_type,
            category=row.category,
            name=row.name,
        )
    return NodeDefinitionResponse(
        node_type=row.node_type,
        category=row.category,
        name=row.name,
        description=row.description or "",
        icon=row.icon or "📦",
        contract_version=cv_str,
        contract=contract_obj,
        enabled=row.enabled,
        is_custom=row.is_custom,
    )


# ===== 端点 =====
# 顺序: 列表 → POST /sync → PUT /{node_type}/enable → ... → 最后是 GET /{node_type} (catch-all)


@router.get(
    "",
    response_model=NodeDefinitionListResponse,
    summary="列出全部节点定义",
)
async def list_node_definitions(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    category: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=128),
    enabled_only: bool = Query(default=True),
    include_contract: bool = Query(default=True),
    sort_by: Literal["node_type", "category", "name", "updated_at"] = Query(default="category"),
    sort_order: Literal["asc", "desc"] = Query(default="asc"),
) -> NodeDefinitionListResponse:
    """列出节点定义 (合并系统 + 自定义)."""
    stmt = select(NodeDefinition)
    if enabled_only:
        stmt = stmt.where(NodeDefinition.enabled.is_(True))
    if category:
        stmt = stmt.where(NodeDefinition.category == category)
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            (NodeDefinition.name.ilike(like))
            | (NodeDefinition.description.ilike(like))
            | (NodeDefinition.node_type.ilike(like))
        )

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
        defs.append(_to_node_definition_response(row))

    return NodeDefinitionListResponse(definitions=defs)


@router.post(
    "/sync",
    response_model=SyncResultResponse,
    summary="从 NodeRegistry 重新同步系统节点",
    description=(
        "重新触发 NodeRegistry → DB 的同步逻辑. 仅同步系统节点 (is_custom=false), "
        "不影响自定义节点. 适用于代码升级后节点定义变化但未重启服务的场景."
    ),
    dependencies=[__import__("fastapi").Depends(require_role(Role.SUPER_ADMIN))],
)
async def sync_node_definitions(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
) -> SyncResultResponse:
    """同步系统节点 (super_admin only)."""
    # 触发 nodes 包的导入以确保所有节点已注册
    from hscredit_studio import nodes as _nodes_pkg  # noqa: F401
    contracts = NodeRegistry.list_contracts()
    registry_map: dict[str, Any] = {c.node_type: c for c in contracts}

    # DB 现状
    rows = (await session.scalars(
        select(NodeDefinition).where(NodeDefinition.is_custom.is_(False))
    )).all()
    db_map = {r.node_type: r for r in rows}

    added = updated = removed = 0

    for nt, contract in registry_map.items():
        contract_dict = contract.model_dump(mode="json")
        contract_dict["node_type"] = contract.node_type
        if nt in db_map:
            row = db_map[nt]
            row.contract = contract_dict
            row.contract_version = 2
            updated += 1
        else:
            cat_val = contract.category
            if not isinstance(cat_val, str):
                cat_val = cat_val.value
            nd = NodeDefinition(
                node_type=nt,
                category=cat_val,
                name=contract.name,
                description=contract.description or "",
                icon=contract.icon or "📦",
                contract_version=2,
                contract=contract_dict,
                enabled=True,
                is_custom=False,
                source="system",
                meta_editable=False,
                owner_tenant_id=None,
            )
            session.add(nd)
            added += 1

    # 软删除: DB 有但 registry 没有
    for nt in list(db_map.keys()):
        if nt not in registry_map:
            row = db_map[nt]
            row.enabled = False
            removed += 1

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        _log.error("node_sync_failed", error=str(e)[:200])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "E_NODE_SYNC_FAILED",
                "message": f"同步失败: {type(e).__name__}: {str(e)[:200]}",
            },
        )

    # 审计日志 (独立 try, 失败不影响主流程)
    try:
        await record_event(
            session,
            tenant_id=tenant_id,
            user_id=user.get("user_id"),
            action="node_definition.sync",
            resource_type="node_definition",
            resource_id=None,
            details={"added": added, "updated": updated, "removed": removed, "total": len(contracts)},
        )
        await session.commit()
    except Exception as audit_err:
        _log.warning("audit_write_failed", error=str(audit_err)[:200])
        try:
            await session.rollback()
        except Exception:
            pass

    _log.info(
        "node_definitions_synced",
        added=added,
        updated=updated,
        removed=removed,
        total=len(contracts),
    )

    return SyncResultResponse(
        synced=len(contracts),
        added=added,
        updated=updated,
        removed=removed,
    )


@router.put(
    "/{node_type}/enable",
    response_model=NodeToggleResponse,
    summary="启用节点",
    dependencies=[__import__("fastapi").Depends(require_role(Role.SUPER_ADMIN))],
)
async def enable_node(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    node_type: str,
) -> NodeToggleResponse:
    """启用节点 (super_admin only)."""
    nd = await _get_node_definition_or_404(session, node_type)
    if nd.enabled:
        return NodeToggleResponse(
            node_type=node_type,
            enabled=True,
            updated_at=nd.updated_at.isoformat() if nd.updated_at else "",
        )
    nd.enabled = True
    await session.commit()
    await session.refresh(nd)

    try:
        await record_event(
            session,
            tenant_id=tenant_id,
            user_id=user.get("user_id"),
            action="node_definition.enabled",
            resource_type="node_definition",
            resource_id=None,
            details={"node_type": node_type, "enabled": True},
        )
        await session.commit()
    except Exception as e:
        _log.warning("audit_write_failed", error=str(e)[:200])

    _log.info("node_enabled", node_type=node_type)
    return NodeToggleResponse(
        node_type=node_type,
        enabled=True,
        updated_at=nd.updated_at.isoformat(),
    )


@router.put(
    "/{node_type}/disable",
    response_model=NodeToggleResponse,
    summary="停用节点",
    dependencies=[__import__("fastapi").Depends(require_role(Role.SUPER_ADMIN))],
)
async def disable_node(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    node_type: str,
) -> NodeToggleResponse:
    """停用节点 (super_admin only)."""
    nd = await _get_node_definition_or_404(session, node_type)
    if not nd.enabled:
        return NodeToggleResponse(
            node_type=node_type,
            enabled=False,
            updated_at=nd.updated_at.isoformat() if nd.updated_at else "",
        )
    nd.enabled = False
    await session.commit()
    await session.refresh(nd)

    try:
        await record_event(
            session,
            tenant_id=tenant_id,
            user_id=user.get("user_id"),
            action="node_definition.disabled",
            resource_type="node_definition",
            resource_id=None,
            details={"node_type": node_type, "enabled": False},
        )
        await session.commit()
    except Exception as e:
        _log.warning("audit_write_failed", error=str(e)[:200])

    _log.info("node_disabled", node_type=node_type)
    return NodeToggleResponse(
        node_type=node_type,
        enabled=False,
        updated_at=nd.updated_at.isoformat(),
    )


@router.put(
    "/{node_type}/meta",
    response_model=NodeDefinitionResponse,
    summary="更新节点元数据",
    description="更新 name/description/icon. 不影响 contract 和代码.",
    dependencies=[__import__("fastapi").Depends(require_role(Role.SUPER_ADMIN))],
)
async def update_node_meta(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    node_type: str,
    payload: NodeMetaUpdateRequest,
) -> NodeDefinitionResponse:
    """更新节点元数据 (super_admin only)."""
    nd = await _get_node_definition_or_404(session, node_type)

    changed_fields: dict[str, Any] = {}
    if payload.name is not None and payload.name != nd.name:
        changed_fields["name"] = (nd.name, payload.name)
        nd.name = payload.name
    if payload.description is not None and payload.description != nd.description:
        changed_fields["description"] = (nd.description, payload.description)
        nd.description = payload.description
    if payload.icon is not None and payload.icon != nd.icon:
        changed_fields["icon"] = (nd.icon, payload.icon)
        nd.icon = payload.icon

    if not changed_fields:
        return _to_node_definition_response(nd)

    await session.commit()
    await session.refresh(nd)

    try:
        await record_event(
            session,
            tenant_id=tenant_id,
            user_id=user.get("user_id"),
            action="node_definition.meta_updated",
            resource_type="node_definition",
            resource_id=None,
            details={"node_type": node_type, "changes": changed_fields},
        )
        await session.commit()
    except Exception as e:
        _log.warning("audit_write_failed", error=str(e)[:200])

    _log.info(
        "node_meta_updated",
        node_type=node_type,
        changes=list(changed_fields.keys()),
    )
    return _to_node_definition_response(nd)


# 单节点详情 — 必须在最末尾, /{node_type} 是 catch-all 会拦截其它路径
@router.get(
    "/{node_type}",
    response_model=NodeDefinitionResponse,
    summary="单节点详情",
)
async def get_node_definition(
    session: SessionDep,
    tenant_id: TenantDep,
    user: CurrentUserDep,
    node_type: str,
) -> NodeDefinitionResponse:
    """按 node_type 返回节点定义详情 (含完整 contract)."""
    nd = await _get_node_definition_or_404(session, node_type)
    return _to_node_definition_response(nd)


__all__ = ["router"]