"""评分卡与规则类节点 — 评分卡训练、圆整、规则挖掘.

导入本包会触发各节点模块的 ``@register_node`` 装饰器,
把节点类注册到 :class:`hscredit_studio.nodes.registry.NodeRegistry`.
"""
from __future__ import annotations

from hscredit_studio.nodes.scorecard_rule import (
    round_score_card,
    score_card,
)

__all__ = [
    "score_card",
    "round_score_card",
]
