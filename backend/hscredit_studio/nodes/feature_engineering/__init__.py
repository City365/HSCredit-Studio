"""特征工程类节点 — 表达式衍生、分箱、编码.

导入本包会触发各节点模块的 ``@register_node`` 装饰器,
把节点类注册到 :class:`hscredit_studio.nodes.registry.NodeRegistry`.
"""

from __future__ import annotations

from hscredit_studio.nodes.feature_engineering import (
    num_expr_derive,
    optimal_binning_cart,
    optimal_binning_chi,
    woe_encoder,
)

__all__ = [
    "num_expr_derive",
    "optimal_binning_cart",
    "optimal_binning_chi",
    "woe_encoder",
]
