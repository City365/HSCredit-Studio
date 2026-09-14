"""自定义节点 Service — Phase 6 B36.

封装所有业务逻辑:
- CRUD: create / get / list / update_meta / soft_delete
- 版本: update_code / list_versions / get_version / rollback
- 草稿: get_draft / save_draft / discard_draft
- 锁: acquire_lock / release_lock / heartbeat
- 校验/反推/试运行: validate / detect_contract / test
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.exceptions import (
    NodeTypeConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from hscredit_studio.core.logging import get_logger
from hscredit_studio.models import (
    CustomNode,
    CustomNodeTestRun,
    CustomNodeVersion,
    NodeDefinition,
    NodeDefinitionDraft,
    NodeDefinitionLock,
)
from hscredit_studio.schemas.node_contract import NodeContract

_log = get_logger(__name__)


# ===== 配置 =====


LOCK_TTL_SEC = 300  # 5 分钟
DRAFT_RETENTION_DAYS = 30


# ===== 错误辅助 =====


def _cn_or_404(cn: CustomNode | None, msg: str = "custom_node not found") -> CustomNode:
    if cn is None:
        raise ResourceNotFoundError(msg)
    return cn


def _ver_or_404(v: CustomNodeVersion | None, msg: str = "version not found") -> CustomNodeVersion:
    if v is None:
        raise ResourceNotFoundError(msg)
    return v


# ===== 节点 CRUD =====


async def create_node(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    node_type: str,
    name: str,
    category: str,
    description: str | None,
    icon: str | None,
    visibility: str,
    code: str,
    contract: NodeContract,
    requirements: str | None,
) -> CustomNode:
    """创建自定义节点 + v1 版本."""
    # 检查 node_type 唯一性 (per tenant)
    existing = (
        await session.scalars(
            select(CustomNode).where(
                CustomNode.tenant_id == tenant_id,
                CustomNode.node_type == node_type,
                CustomNode.deleted_at.is_(None),
            )
        )
    ).first()
    if existing is not None:
        raise NodeTypeConflictError(
            f"节点类型 {node_type} 在本租户已存在",
            details={"tenant_id": str(tenant_id), "node_type": node_type},
        )

    # 同步创建 node_definitions 记录 (供前端节点库)
    contract_dict = contract.model_dump(mode="json")
    contract_dict["node_type"] = contract.node_type

    try:
        cn = CustomNode(
            tenant_id=tenant_id,
            node_type=node_type,
            name=name,
            visibility=visibility,
            code=code,
            requirements=requirements,
            contract=contract_dict,
            created_by=user_id,
            enabled=True,
            icon=icon or "🛠️",
            description=description,
            category=category,
            current_version_number=1,
        )
        session.add(cn)
        await session.flush()  # 获取 cn.custom_node_id

        v1 = CustomNodeVersion(
            custom_node_id=cn.custom_node_id,
            version_number=1,
            code=code,
            contract=contract_dict,
            requirements=requirements,
            change_summary="初始版本",
            created_by=user_id,
        )
        session.add(v1)
        await session.flush()

        # 创建 node_definitions (供前端节点库统一展示)
        nd = NodeDefinition(
            node_type=node_type,
            category=category,
            name=name,
            description=description or "",
            icon=icon or "🛠️",
            contract_version=2,
            contract=contract_dict,
            enabled=True,
            is_custom=True,
            source="custom",
            meta_editable=True,
            owner_tenant_id=tenant_id,
        )
        session.add(nd)

        await session.commit()
        await session.refresh(cn)
        _log.info(
            "custom_node_created",
            custom_node_id=str(cn.custom_node_id),
            tenant_id=str(tenant_id),
            node_type=node_type,
            user_id=str(user_id),
        )

        # Phase 6 B36: 发布 reload 消息, 让所有 worker 加载新节点
        try:
            from hscredit_studio.services.node_pubsub import publish_node_reload
            await publish_node_reload(node_type, action="reload")
        except Exception as e:
            _log.warning("node_reload_publish_failed_on_create", error=str(e)[:200])

        return cn

    except IntegrityError as e:
        await session.rollback()
        raise NodeTypeConflictError(
            f"节点类型 {node_type} 已存在",
            details={"db_error": str(e.orig)},
        ) from e


async def get_node(
    session: AsyncSession,
    *,
    custom_node_id: uuid.UUID,
    tenant_id: uuid.UUID | None = None,
) -> CustomNode:
    """按 ID 取节点."""
    stmt = select(CustomNode).where(
        CustomNode.custom_node_id == custom_node_id,
        CustomNode.deleted_at.is_(None),
    )
    if tenant_id is not None:
        stmt = stmt.where(CustomNode.tenant_id == tenant_id)
    cn = (await session.scalars(stmt)).first()
    return _cn_or_404(cn, f"custom_node {custom_node_id} not found")


async def get_node_by_type(
    session: AsyncSession,
    *,
    node_type: str,
    tenant_id: uuid.UUID,
) -> CustomNode | None:
    """按 node_type 取本租户的节点 (供 internal 联动)."""
    stmt = select(CustomNode).where(
        CustomNode.tenant_id == tenant_id,
        CustomNode.node_type == node_type,
        CustomNode.deleted_at.is_(None),
    )
    return (await session.scalars(stmt)).first()


async def list_nodes(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    category: str | None = None,
    visibility: str | None = None,
    enabled_only: bool = True,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[CustomNode], int]:
    """列出本租户的自定义节点."""
    stmt = select(CustomNode).where(
        CustomNode.tenant_id == tenant_id,
        CustomNode.deleted_at.is_(None),
    )
    if enabled_only:
        stmt = stmt.where(CustomNode.enabled.is_(True))
    if category:
        stmt = stmt.where(CustomNode.category == category)
    if visibility:
        stmt = stmt.where(CustomNode.visibility == visibility)
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            (CustomNode.name.ilike(like))
            | (CustomNode.description.ilike(like))
            | (CustomNode.node_type.ilike(like))
        )

    # 总数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.scalar(count_stmt)) or 0

    # 分页
    stmt = stmt.order_by(CustomNode.updated_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.scalars(stmt)).all()
    return list(rows), total


async def update_node_meta(
    session: AsyncSession,
    *,
    custom_node_id: uuid.UUID,
    tenant_id: uuid.UUID,
    name: str | None = None,
    category: str | None = None,
    description: str | None = None,
    icon: str | None = None,
    visibility: str | None = None,
    enabled: bool | None = None,
) -> CustomNode:
    """更新节点元数据 (不含 code)."""
    cn = await get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    changed: dict[str, Any] = {}
    if name is not None and name != cn.name:
        changed["name"] = (cn.name, name)
        cn.name = name
    if category is not None and category != cn.category:
        changed["category"] = (cn.category, category)
        cn.category = category
    if description is not None and description != cn.description:
        changed["description"] = (cn.description, description)
        cn.description = description
    if icon is not None and icon != cn.icon:
        changed["icon"] = (cn.icon, icon)
        cn.icon = icon
    if visibility is not None and visibility != cn.visibility:
        changed["visibility"] = (cn.visibility, visibility)
        cn.visibility = visibility
    if enabled is not None and enabled != cn.enabled:
        changed["enabled"] = (cn.enabled, enabled)
        cn.enabled = enabled

    if not changed:
        return cn

    await session.commit()
    await session.refresh(cn)

    # 同步 node_definitions (前端节点库用)
    nd = await session.get(NodeDefinition, cn.node_type)
    if nd is not None:
        if name is not None:
            nd.name = name
        if category is not None:
            nd.category = category
        if description is not None:
            nd.description = description or ""
        if icon is not None:
            nd.icon = icon or "📦"
        if enabled is not None:
            nd.enabled = enabled
        await session.commit()

    _log.info(
        "custom_node_meta_updated",
        custom_node_id=str(custom_node_id),
        changes=list(changed.keys()),
    )
    return cn


async def soft_delete_node(
    session: AsyncSession,
    *,
    custom_node_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> None:
    """软删除节点 (设置 deleted_at)."""
    cn = await get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    node_type = cn.node_type  # 保存供后续使用
    cn.deleted_at = datetime.utcnow()
    cn.enabled = False
    # 同步 node_definitions: 软删除 (enabled=false)
    nd = await session.get(NodeDefinition, node_type)
    if nd is not None:
        nd.enabled = False
    await session.commit()
    _log.info(
        "custom_node_deleted",
        custom_node_id=str(custom_node_id),
        node_type=node_type,
    )

    # Phase 6 B36: 发布 remove 消息, 让所有 worker 卸载
    try:
        from hscredit_studio.services.node_pubsub import publish_node_reload
        await publish_node_reload(node_type, action="remove")
    except Exception as e:
        _log.warning("node_reload_publish_failed_on_delete", error=str(e)[:200])


# ===== 版本管理 =====


async def update_code(
    session: AsyncSession,
    *,
    custom_node_id: uuid.UUID,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    code: str,
    contract: NodeContract,
    change_summary: str | None,
) -> CustomNodeVersion:
    """提交新版本代码. 自动分配 version_number = max + 1."""
    cn = await get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    if cn.deleted_at is not None:
        raise ValidationError("已删除的节点不能提交新版本")

    # 取最大版本号
    max_v = (
        await session.scalar(
            select(func.coalesce(func.max(CustomNodeVersion.version_number), 0)).where(
                CustomNodeVersion.custom_node_id == custom_node_id
            )
        )
    ) or 0
    next_v = int(max_v) + 1

    contract_dict = contract.model_dump(mode="json")
    contract_dict["node_type"] = contract.node_type

    ver = CustomNodeVersion(
        custom_node_id=custom_node_id,
        version_number=next_v,
        code=code,
        contract=contract_dict,
        requirements=cn.requirements,
        change_summary=change_summary,
        created_by=user_id,
    )
    session.add(ver)
    await session.flush()

    # 更新 cn 的 current version + code
    cn.code = code
    cn.contract = contract_dict
    cn.current_version_number = next_v
    await session.commit()
    await session.refresh(ver)

    # 同步 node_definitions 的 contract
    nd = await session.get(NodeDefinition, cn.node_type)
    if nd is not None:
        nd.contract = contract_dict
        nd.contract_version = 2
        await session.commit()

    # Phase 6 B36: 发布 reload 消息, 让所有 worker 同步
    try:
        from hscredit_studio.services.node_pubsub import publish_node_reload
        await publish_node_reload(cn.node_type, action="reload")
    except Exception as e:
        _log.warning("node_reload_publish_failed", error=str(e)[:200])

    _log.info(
        "custom_node_version_created",
        custom_node_id=str(custom_node_id),
        version_id=str(ver.version_id),
        version_number=next_v,
    )
    return ver


async def list_versions(
    session: AsyncSession,
    *,
    custom_node_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> list[CustomNodeVersion]:
    """列出所有版本 (按 version_number 倒序)."""
    cn = await get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    rows = (
        await session.scalars(
            select(CustomNodeVersion)
            .where(CustomNodeVersion.custom_node_id == cn.custom_node_id)
            .order_by(CustomNodeVersion.version_number.desc())
        )
    ).all()
    return list(rows)


async def get_version(
    session: AsyncSession,
    *,
    custom_node_id: uuid.UUID,
    version_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> CustomNodeVersion:
    """取指定版本."""
    cn = await get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    v = await session.get(CustomNodeVersion, version_id)
    if v is None or v.custom_node_id != cn.custom_node_id:
        raise ResourceNotFoundError(f"version {version_id} not found")
    return v


async def rollback(
    session: AsyncSession,
    *,
    custom_node_id: uuid.UUID,
    version_id: uuid.UUID,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> CustomNodeVersion:
    """回滚到指定版本. 创建一个新版本 (内容 = 目标版本), 不删除历史."""
    cn = await get_node(session, custom_node_id=custom_node_id, tenant_id=tenant_id)
    target = await get_version(
        session, custom_node_id=custom_node_id, version_id=version_id, tenant_id=tenant_id
    )
    # 复用 update_code 逻辑, 但 change_summary 标注回滚
    new_ver = await update_code(
        session,
        custom_node_id=cn.custom_node_id,
        tenant_id=tenant_id,
        user_id=user_id,
        code=target.code,
        contract=NodeContract.model_validate(target.contract),
        change_summary=f"回滚到 v{target.version_number}",
    )
    _log.info(
        "custom_node_rolled_back",
        custom_node_id=str(cn.custom_node_id),
        target_version=target.version_number,
        new_version=new_ver.version_number,
    )
    return new_ver


# ===== 草稿 =====


async def get_draft(
    session: AsyncSession,
    *,
    custom_node_id: uuid.UUID,
) -> NodeDefinitionDraft | None:
    """取草稿 (无则返回 None)."""
    return (
        await session.scalars(
            select(NodeDefinitionDraft).where(
                NodeDefinitionDraft.custom_node_id == custom_node_id
            )
        )
    ).first()


async def save_draft(
    session: AsyncSession,
    *,
    custom_node_id: uuid.UUID,
    code: str,
    contract_preview: dict[str, Any] | None,
    validation_status: str,
    validation_issues: dict[str, Any] | None,
) -> NodeDefinitionDraft:
    """保存/更新草稿 (upsert)."""
    draft = await get_draft(session, custom_node_id=custom_node_id)
    now = datetime.utcnow()
    if draft is None:
        draft = NodeDefinitionDraft(
            custom_node_id=custom_node_id,
            draft_code=code,
            draft_contract={},
            contract_preview=contract_preview,
            validation_status=validation_status,
            validation_issues=validation_issues,
            last_validation_at=now,
        )
        session.add(draft)
    else:
        draft.draft_code = code
        draft.contract_preview = contract_preview
        draft.validation_status = validation_status
        draft.validation_issues = validation_issues
        draft.last_validation_at = now
    await session.commit()
    await session.refresh(draft)
    return draft


async def discard_draft(
    session: AsyncSession,
    *,
    custom_node_id: uuid.UUID,
) -> None:
    """删除草稿."""
    draft = await get_draft(session, custom_node_id=custom_node_id)
    if draft is not None:
        await session.delete(draft)
        await session.commit()


# ===== 编辑锁 =====


async def acquire_lock(
    session: AsyncSession,
    *,
    node_type: str,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> NodeDefinitionLock:
    """申请编辑锁. 如果已被他人占用, 抛 409."""
    # 检查已有锁
    existing = (
        await session.scalars(
            select(NodeDefinitionLock).where(
                NodeDefinitionLock.node_type == node_type,
                NodeDefinitionLock.tenant_id == tenant_id,
            )
        )
    ).first()

    now = datetime.utcnow()
    if existing is not None:
        if existing.expires_at > now and existing.locked_by != user_id:
            raise NodeTypeConflictError(
                f"节点 {node_type} 正在被他人编辑",
                details={
                    "node_type": node_type,
                    "locked_by": str(existing.locked_by),
                    "expires_at": existing.expires_at.isoformat(),
                },
            )
        # 锁已过期, 或被同一用户持有 → 续期
        existing.locked_by = user_id
        existing.locked_at = now
        existing.expires_at = now + timedelta(seconds=LOCK_TTL_SEC)
        await session.commit()
        await session.refresh(existing)
        return existing

    # 新建锁
    lock = NodeDefinitionLock(
        node_type=node_type,
        tenant_id=tenant_id,
        locked_by=user_id,
        locked_at=now,
        expires_at=now + timedelta(seconds=LOCK_TTL_SEC),
    )
    session.add(lock)
    await session.commit()
    await session.refresh(lock)
    return lock


async def release_lock(
    session: AsyncSession,
    *,
    node_type: str,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """释放编辑锁 (主动释放, 不检查是否过期)."""
    lock = (
        await session.scalars(
            select(NodeDefinitionLock).where(
                NodeDefinitionLock.node_type == node_type,
                NodeDefinitionLock.tenant_id == tenant_id,
            )
        )
    ).first()
    if lock is None:
        return
    # 只允许锁持有者释放
    if lock.locked_by != user_id:
        raise NodeTypeConflictError(
            "只有锁持有者可以释放锁",
            details={"node_type": node_type},
        )
    await session.delete(lock)
    await session.commit()


async def heartbeat_lock(
    session: AsyncSession,
    *,
    node_type: str,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> NodeDefinitionLock:
    """心跳续期."""
    lock = (
        await session.scalars(
            select(NodeDefinitionLock).where(
                NodeDefinitionLock.node_type == node_type,
                NodeDefinitionLock.tenant_id == tenant_id,
            )
        )
    ).first()
    if lock is None or lock.locked_by != user_id:
        raise ResourceNotFoundError(f"lock for {node_type} not found or not owned by you")
    lock.expires_at = datetime.utcnow() + timedelta(seconds=LOCK_TTL_SEC)
    await session.commit()
    await session.refresh(lock)
    return lock


# ===== 试运行历史 =====


async def record_test_run(
    session: AsyncSession,
    *,
    custom_node_id: uuid.UUID,
    tenant_id: uuid.UUID,
    version_id: uuid.UUID,
    triggered_by: uuid.UUID | None,
    status: str,
    log: str | None,
    duration_ms: int,
) -> CustomNodeTestRun:
    """记录一次试运行."""
    tr = CustomNodeTestRun(
        custom_node_id=custom_node_id,
        version_id=version_id,
        tenant_id=tenant_id,
        triggered_by=triggered_by,
        status=status,
        log=log,
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
    )
    session.add(tr)
    await session.commit()
    await session.refresh(tr)
    return tr


__all__ = [
    "DRAFT_RETENTION_DAYS",
    "LOCK_TTL_SEC",
    "acquire_lock",
    "create_node",
    "discard_draft",
    "get_draft",
    "get_node",
    "get_node_by_type",
    "get_version",
    "heartbeat_lock",
    "list_nodes",
    "list_versions",
    "record_test_run",
    "release_lock",
    "rollback",
    "save_draft",
    "soft_delete_node",
    "update_code",
    "update_node_meta",
]
