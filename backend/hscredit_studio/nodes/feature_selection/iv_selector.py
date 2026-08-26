"""IV 阈值筛选 — 按 IV >= threshold 保留特征.

复用 ``hscredit.core.selectors.IVSelector``;``exclude`` 用于强制排除
特定列(如 ID 列、时间列)。
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from hscredit_studio.core.exceptions import (
    DependencyError,
    ValidationError,
)
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.nodes.registry import register_node
from hscredit_studio.schemas.node_contract import (
    CacheConfig,
    NodeContract,
    ParamSpec,
    PortSchema,
)


@register_node
class IVSelectorNode(BaseNode):
    """基于 IV 阈值的特征筛选."""

    contract = NodeContract(
        node_type="iv_selector",
        category="特征筛选",
        name="IV 筛选",
        description="按 IV 阈值筛选有效特征",
        icon="🔬",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["woe_df", "selected_df", "binned_df"])],
        outputs=[
            PortSchema(name="selector", type="SelectorArtifact", description="训练好的 IV 筛选器"),
            PortSchema(name="selected_df", type="DataFrame", description="筛选后的 DataFrame"),
        ],
        params=[
            ParamSpec(name="target", type="str", label="目标列名", required=True),
            ParamSpec(
                name="threshold",
                type="float",
                label="IV 阈值",
                default=0.02,
                min=0.0,
                max=1.0,
                step=0.01,
            ),
            ParamSpec(
                name="exclude",
                type="list",
                label="强制排除列",
                default=[],
                advanced=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=300,
        estimated_duration_sec=30,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        try:
            from hscredit.core.selectors import IVSelector
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.selectors.IVSelector 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        df = inputs.get("df")
        if df is None:
            df = inputs.get("woe_df")
        if df is None:
            df = inputs.get("selected_df")
        if df is None:
            df = inputs.get("binned_df")
        if df is None or not hasattr(df, "columns"):
            raise ValidationError(
                "缺少 DataFrame 输入（df/woe_df/selected_df/binned_df）",
                details={"node_type": self.contract.node_type, "available_inputs": list(inputs.keys())},
            )
        target = params["target"]
        if target not in df.columns:
            raise ValidationError(
                f"目标列 {target} 不存在",
                details={"node_type": self.contract.node_type, "target": target},
            )
        if df[target].nunique() < 2:
            raise ValidationError(
                f"目标列 {target} 需要至少 2 个类别",
                details={"node_type": self.contract.node_type, "target": target},
            )

        exclude = params.get("exclude") or []
        selector = IVSelector(
            target=target,
            threshold=float(params.get("threshold", 0.02)),
            exclude=exclude or None,
        )
        try:
            selector.fit(df)
        except Exception as e:
            raise ValidationError(
                f"IV 筛选器 fit 失败: {e}",
                details={"node_type": self.contract.node_type, "target": target},
            ) from e
        try:
            selected_df = selector.transform(df)
        except Exception as e:
            raise ValidationError(
                f"IV 筛选 transform 失败: {e}",
                details={"node_type": self.contract.node_type},
            ) from e
        return {"selector": selector, "selected_df": selected_df}
