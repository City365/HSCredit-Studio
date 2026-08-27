"""特征筛选类节点 — IV、VIF 等单维度/共线性筛选.

导入本包会触发各节点模块的 ``@register_node`` 装饰器,
把节点类注册到 :class:`hscredit_studio.nodes.registry.NodeRegistry`.
"""

from __future__ import annotations

from hscredit_studio.nodes.feature_selection import (
    iv_selector,
    vif_selector,
)

__all__ = [
    "iv_selector",
    "vif_selector",
]
