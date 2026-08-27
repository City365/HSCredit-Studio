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

# 触发各分类子模块的导入,执行其中的 @register_node 装饰器。
from hscredit_studio.nodes.data_ingest import (
    csv_ingest,
    excel_ingest,
    field_type_infer,
    reject_inference,
    train_oot_split,
)
from hscredit_studio.nodes.eda import (
    iv_analysis,
    missing_rate,
)
from hscredit_studio.nodes.feature_engineering import (
    num_expr_derive,
    optimal_binning_cart,
    optimal_binning_chi,
    woe_encoder,
)
from hscredit_studio.nodes.feature_selection import (
    iv_selector,
    vif_selector,
)
from hscredit_studio.nodes.model_training import (
    logistic_regression,
    shap_explanation,
    xgboost,
)
from hscredit_studio.nodes.registry import NodeRegistry, register_node
from hscredit_studio.nodes.report_deploy import (
    excel_export,
    model_report,
)
from hscredit_studio.nodes.scorecard_rule import (
    round_score_card,
    score_card,
)

__all__ = [
    "BaseNode",
    "NodeRegistry",
    # 数据接入
    "csv_ingest",
    "excel_export",
    "excel_ingest",
    "field_type_infer",
    "iv_analysis",
    # 特征筛选
    "iv_selector",
    # 模型训练
    "logistic_regression",
    # EDA
    "missing_rate",
    # 报告与部署
    "model_report",
    # 特征工程
    "num_expr_derive",
    "optimal_binning_cart",
    "optimal_binning_chi",
    "register_node",
    "reject_inference",
    "round_score_card",
    # 评分卡与规则
    "score_card",
    "shap_explanation",
    "train_oot_split",
    "vif_selector",
    "woe_encoder",
    "xgboost",
]
