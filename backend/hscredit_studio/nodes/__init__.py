"""节点库 — 所有 hscredit 业务节点的封装.

导入本包会自动触发所有分类子模块的导入,
分类子模块又通过 ``@register_node`` 装饰器把具体节点类注册到
:class:`hscredit_studio.nodes.registry.NodeRegistry`.

典型用法::

    from hscredit_studio.nodes import NodeRegistry
    from hscredit_studio.nodes.registry import register_node
    from hscredit_studio.nodes.base import BaseNode

    @register_node
    class MyNode(BaseNode):
        contract = NodeContract(node_type="my_node", category="EDA", name="我的节点")
        def run(self, inputs, params):
            return {"result": 42}

    cls = NodeRegistry.get("my_node")
    instance = cls()
    outputs = instance.run({}, {})
"""
from __future__ import annotations

from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.nodes.registry import NodeRegistry, register_node

# 触发各分类子模块的导入,执行其中的 @register_node 装饰器。
from hscredit_studio.nodes.data_ingest import (
    csv_ingest,
    excel_ingest,
    train_oot_split,
    field_type_infer,
)
from hscredit_studio.nodes.eda import (
    missing_rate,
    iv_analysis,
)
from hscredit_studio.nodes.feature_engineering import (
    num_expr_derive,
    optimal_binning_chi,
    optimal_binning_cart,
    woe_encoder,
)
from hscredit_studio.nodes.feature_selection import (
    iv_selector,
    vif_selector,
)
from hscredit_studio.nodes.model_training import (
    logistic_regression,
)
from hscredit_studio.nodes.scorecard_rule import (
    score_card,
    round_score_card,
)
from hscredit_studio.nodes.report_deploy import (
    model_report,
    excel_export,
)

__all__ = [
    "BaseNode",
    "NodeRegistry",
    "register_node",
    # 数据接入
    "csv_ingest",
    "excel_ingest",
    "train_oot_split",
    "field_type_infer",
    # EDA
    "missing_rate",
    "iv_analysis",
    # 特征工程
    "num_expr_derive",
    "optimal_binning_chi",
    "optimal_binning_cart",
    "woe_encoder",
    # 特征筛选
    "iv_selector",
    "vif_selector",
    # 模型训练
    "logistic_regression",
    # 评分卡与规则
    "score_card",
    "round_score_card",
    # 报告与部署
    "model_report",
    "excel_export",
]
