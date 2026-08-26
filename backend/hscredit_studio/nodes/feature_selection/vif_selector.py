"""VIF 共线性筛选 — 迭代剔除 VIF 最大的特征.

复用 ``hscredit.core.selectors.VIFSelector``;``threshold`` 默认 4.0,
大于该阈值的特征将被迭代剔除, 直至剩余特征 VIF <= threshold。

VIF 筛选无需目标列(共线性计算仅依赖特征矩阵)。
"""
from __future__ import annotations

from typing import Any

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
class VIFSelectorNode(BaseNode):
    """基于方差膨胀因子的特征筛选."""

    contract = NodeContract(
        node_type="vif_selector",
        category="特征筛选",
        name="VIF 筛选",
        description="按 VIF 阈值迭代剔除共线性特征",
        icon="📉",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["woe_df", "selected_df", "binned_df"])],
        outputs=[
            PortSchema(name="selector", type="SelectorArtifact", description="训练好的 VIF 筛选器"),
            PortSchema(name="selected_df", type="DataFrame", description="筛选后的 DataFrame"),
        ],
        params=[
            ParamSpec(
                name="threshold",
                type="float",
                label="VIF 阈值",
                default=4.0,
                min=1.0,
                max=50.0,
                step=0.5,
            ),
            ParamSpec(
                name="exclude",
                type="list",
                label="强制排除列",
                default=[],
                advanced=True,
            ),
            ParamSpec(
                name="max_iter",
                type="int",
                label="最大迭代次数",
                default=100,
                min=1,
                max=1000,
                advanced=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=600,
        estimated_duration_sec=60,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        try:
            from hscredit.core.selectors import VIFSelector
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.selectors.VIFSelector 不可用: {e}",
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
        # VIF 筛选无需 target 列, 默认传 'target' 以满足基类要求。
        target = params.get("target", "target")

        exclude = params.get("exclude") or []
        selector = VIFSelector(
            target=target,
            threshold=float(params.get("threshold", 4.0)),
            exclude=exclude or None,
            max_iter=int(params.get("max_iter", 100)),
        )
        try:
            selector.fit(df)
            selected_df = selector.transform(df)
        except Exception as e:
            raise ValidationError(
                f"VIF 筛选失败: {e}",
                details={"node_type": self.contract.node_type},
            ) from e
        return {"selector": selector, "selected_df": selected_df}
