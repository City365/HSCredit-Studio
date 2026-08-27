"""模型训练类节点 — 逻辑回归、Boosting 等.

导入本包会触发各节点模块的 ``@register_node`` 装饰器,
把节点类注册到 :class:`hscredit_studio.nodes.registry.NodeRegistry`.
"""

from __future__ import annotations

from hscredit_studio.nodes.model_training import (
    logistic_regression,
)

__all__ = [
    "logistic_regression",
]
