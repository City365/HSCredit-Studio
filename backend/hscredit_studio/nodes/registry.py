"""节点注册表 — 管理所有可用的节点类型.

设计要点(依据 :file:`docs/design/01-system-architecture.md` 第 1.5 节):

- 全局单例(:data:`NodeRegistry._nodes`),按 ``node_type`` 索引节点类。
- 节点类通过 :func:`register_node` 装饰器或 :meth:`NodeRegistry.register` 显式注册。
- 提供 ``list_by_category`` / ``list_contracts`` 用于节点库渲染。
- 重复注册同名节点会抛错,避免静默覆盖。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from hscredit_studio.core.exceptions import NodeNotFoundError
from hscredit_studio.schemas.node_contract import NodeCategory, NodeContract

if TYPE_CHECKING:
    from hscredit_studio.nodes.base import BaseNode


class NodeRegistry:
    """节点注册表 — 全局单例.

    用法::

        # 节点定义时自动注册(通过 @register_node 装饰器)::
        @register_node
        class CsvIngestNode(BaseNode):
            contract = NodeContract(...)

        # 查询时::
        NodeRegistry.get("csv_ingest")  # -> CsvIngestNode 类
        NodeRegistry.list_by_category("数据接入")  # -> [CsvIngestNode, ...]

    说明:本类所有方法都是 ``classmethod``,持有全局字典 ``_nodes``;
    整个进程内任意位置 ``NodeRegistry.get(...)`` 都能拿到相同结果。
    """

    _nodes: ClassVar[dict[str, type[BaseNode]]] = {}

    @classmethod
    def register(cls, node_cls: type[BaseNode]) -> type[BaseNode]:
        """注册节点类 — 通常作为装饰器使用.

        Raises:
            ValueError: 节点类缺少 ``contract`` 类变量,或同 ``node_type`` 已被另一类注册。
        """
        if not hasattr(node_cls, "contract"):
            raise ValueError(f"{node_cls.__name__} 必须定义 contract 类变量")
        contract: NodeContract = node_cls.contract
        if contract.node_type in cls._nodes:
            existing = cls._nodes[contract.node_type]
            if existing is not node_cls:
                raise ValueError(
                    f"节点类型 {contract.node_type} 已被 {existing.__name__} 注册,"
                    f"无法被 {node_cls.__name__} 重新注册"
                )
        cls._nodes[contract.node_type] = node_cls
        return node_cls

    @classmethod
    def unregister(cls, node_type: str) -> None:
        """注销节点(主要用于测试和自定义节点卸载).

        对不存在的 ``node_type`` 是空操作,保证幂等。
        """
        cls._nodes.pop(node_type, None)

    @classmethod
    def get(cls, node_type: str) -> type[BaseNode]:
        """按 ``node_type`` 获取节点类.

        Raises:
            NodeNotFoundError: 节点类型未注册。
        """
        if node_type not in cls._nodes:
            raise NodeNotFoundError(
                f"节点类型 {node_type} 未注册",
                details={"node_type": node_type},
            )
        return cls._nodes[node_type]

    @classmethod
    def try_get(cls, node_type: str) -> type[BaseNode] | None:
        """按 ``node_type`` 获取节点类,未注册返回 ``None``."""
        return cls._nodes.get(node_type)

    @classmethod
    def list_all(cls) -> list[type[BaseNode]]:
        """列出所有已注册节点类(无序,按注册顺序插入)."""
        return list(cls._nodes.values())

    @classmethod
    def list_contracts(cls) -> list[NodeContract]:
        """列出所有节点的契约(用于前端节点库渲染)."""
        return [ncls.contract for ncls in cls._nodes.values()]

    @classmethod
    def list_by_category(cls, category: NodeCategory) -> list[type[BaseNode]]:
        """按分类列出节点."""
        return [ncls for ncls in cls._nodes.values() if ncls.contract.category == category]

    @classmethod
    def count(cls) -> int:
        """已注册节点数量."""
        return len(cls._nodes)

    @classmethod
    def clear(cls) -> None:
        """清空注册表(仅测试用).

        生产代码不应调用;Celery worker 启动时会加载完整节点库,
        清空会导致后续 :meth:`get` 抛 :class:`NodeNotFoundError`。
        """
        cls._nodes.clear()


def register_node(node_cls: type[BaseNode]) -> type[BaseNode]:
    """节点注册装饰器.

    用法::

        @register_node
        class MyNode(BaseNode):
            contract = NodeContract(...)
    """
    return NodeRegistry.register(node_cls)


__all__ = ["NodeRegistry", "register_node"]
