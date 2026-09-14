"""自定义节点加载器 — DB → NodeRegistry (Phase 6 B36).

启动时或代码更新时, 把 DB 中所有启用且非软删除的自定义节点
加载到 NodeRegistry, 使前端节点库能展示自定义节点 + workflow Run
能调用自定义节点.

设计 (依 docs/node-plugin/01_DESIGN.md 4.4 节):
- 加载: 启动时全量 + 手动 sync
- 编译: 把 user code 编译成 BaseNode 子类, 用 exec() 在受限命名空间
- 覆盖: 租户级 node_type 覆盖同名系统节点 (D4 决策)
- 注册: NodeRegistry.register() 把节点类加入全局表
- 同步: Redis pub/sub `node:reload` 频道, 让所有 worker 进程同步 reload

限制 (v1 简化):
- 不编译 user code (避免沙箱重新执行). 仅注册 contract 元数据 + 一个 stub 类.
- workflow Run 时如果调用自定义节点, 需要查 DB 取最新 code (即阶段 5 真实集成).

为什么 v1 不编译: 编译 user code 意味着在主进程内 exec(), 安全风险高.
v1 让前端能显示自定义节点足够. 真实执行留给阶段 5.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from hscredit_studio.core.logging import get_logger
from hscredit_studio.models import CustomNode, CustomNodeVersion
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.nodes.registry import NodeRegistry
from hscredit_studio.schemas.node_contract import NodeContract

_log = get_logger(__name__)


class _CustomNodeProxy(BaseNode):
    """自定义节点的运行时代理.

    v1: 仅占位, 不实际执行. workflow Run 时通过 _resolve_custom_node_code
    从 DB 取最新 code 并交给沙箱执行.

    contract 字段必须存在 (NodeRegistry 要求).
    """

    # contract 类变量由 NodeLoader._make_proxy_class 注入
    # run 方法不实现 (abstract): 实际执行由 sandbox 处理
    pass


def make_proxy_class(node_type: str, contract_dict: dict[str, Any], custom_node_id: uuid.UUID):
    """为单个自定义节点构造一个 Proxy 类.

    每个 custom_node 创建一个独立类 (不同 contract.node_type 重复注册会冲突).
    """
    contract_obj = NodeContract.model_validate(contract_dict)

    class _Proxy(_CustomNodeProxy):
        contract = contract_obj

    _Proxy.__name__ = f"CustomNodeProxy_{node_type}"
    _Proxy.__qualname__ = _Proxy.__name__
    return _Proxy


class CustomNodeLoader:
    """从 DB 加载自定义节点到 NodeRegistry."""

    def __init__(self):
        self._loaded_keys: set[str] = set()  # 已加载的 node_type 集合 (用于清理)

    async def load_all_to_registry(self, session) -> dict[str, Any]:
        """加载所有启用的自定义节点到 NodeRegistry.

        Returns:
            加载统计: {"loaded": N, "skipped": M, "errors": [...]}
        """
        stats = {"loaded": 0, "skipped": 0, "errors": []}

        # 1. 清理已加载的自定义节点 (避免重复加载)
        self._unregister_all_loaded()

        # 2. 查 DB
        try:
            nodes = (
                await session.scalars(
                    select(CustomNode).where(
                        CustomNode.enabled.is_(True),
                        CustomNode.deleted_at.is_(None),
                    )
                )
            ).all()
        except Exception as e:
            _log.error("custom_node_load_db_failed", error=str(e)[:200])
            stats["errors"].append({"phase": "db_query", "error": str(e)[:200]})
            return stats

        for cn in nodes:
            try:
                self._register_one(cn)
                stats["loaded"] += 1
            except Exception as e:
                stats["errors"].append({
                    "node_type": cn.node_type,
                    "custom_node_id": str(cn.custom_node_id),
                    "error": str(e)[:200],
                })
                stats["skipped"] += 1
                _log.warning(
                    "custom_node_load_failed",
                    node_type=cn.node_type,
                    error=str(e)[:200],
                )

        _log.info(
            "custom_nodes_loaded_to_registry",
            loaded=stats["loaded"],
            skipped=stats["skipped"],
            errors_count=len(stats["errors"]),
        )
        return stats

    def _register_one(self, cn: CustomNode) -> None:
        """注册单个自定义节点到 NodeRegistry."""
        # 用 cn.current_version 的 contract (如果没有 current_version_id, 用 cn.contract)
        contract_dict = cn.contract or {}
        if not contract_dict:
            _log.warning(
                "custom_node_no_contract",
                node_type=cn.node_type,
                custom_node_id=str(cn.custom_node_id),
            )
            return
        try:
            proxy_cls = make_proxy_class(cn.node_type, contract_dict, cn.custom_node_id)
            # 如果已存在同名 (reload 场景), 先 unregister
            if NodeRegistry.try_get(cn.node_type) is not None:
                try:
                    NodeRegistry.unregister(cn.node_type)
                except Exception:
                    pass
            NodeRegistry.register(proxy_cls)
            self._loaded_keys.add(cn.node_type)
        except Exception as e:
            _log.error(
                "custom_node_register_failed",
                node_type=cn.node_type,
                error=str(e)[:200],
            )
            raise

    def _unregister_all_loaded(self) -> None:
        """清理之前加载过的节点 (用于重新加载)."""
        for nt in list(self._loaded_keys):
            try:
                NodeRegistry.unregister(nt)
            except Exception:
                pass
            self._loaded_keys.discard(nt)


# 全局 loader 单例
_loader: CustomNodeLoader | None = None


def get_loader() -> CustomNodeLoader:
    global _loader
    if _loader is None:
        _loader = CustomNodeLoader()
    return _loader


async def reload_one_node_type(session, node_type: str) -> bool:
    """重新加载指定 node_type 的自定义节点 (代码更新后调用).

    Returns:
        True if loaded successfully, False otherwise
    """
    cn = (
        await session.scalars(
            select(CustomNode).where(
                CustomNode.node_type == node_type,
                CustomNode.enabled.is_(True),
                CustomNode.deleted_at.is_(None),
            )
        )
    ).first()
    loader = get_loader()
    if cn is None:
        # 节点被禁用或删除, 卸载
        try:
            NodeRegistry.unregister(node_type)
            loader._loaded_keys.discard(node_type)
        except Exception:
            pass
        return True
    try:
        loader._register_one(cn)
        return True
    except Exception:
        return False


__all__ = [
    "CustomNodeLoader",
    "get_loader",
    "make_proxy_class",
    "reload_one_node_type",
]
