"""EDA 类节点 — 探索性数据分析.

导入本包会触发各节点模块的 ``@register_node`` 装饰器,
把节点类注册到 :class:`hscredit_studio.nodes.registry.NodeRegistry`.
"""

from __future__ import annotations

from hscredit_studio.nodes.eda import (
    iv_analysis,
    missing_rate,
)

__all__ = [
    "iv_analysis",
    "missing_rate",
]
