"""CART 最优分箱节点.

``OptimalBinning(method="cart")`` — 基于 CART 决策树的最优分箱,
对齐 ``optbinning`` 预分箱算法,支持 p-value 检验。

实现结构与 ``optimal_binning_chi`` 完全对称, 仅 ``method`` 不同。
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
class OptimalBinningCartNode(BaseNode):
    """使用 CART 决策树的最优分箱."""

    contract = NodeContract(
        node_type="optimal_binning_cart",
        category="特征工程",
        name="CART 分箱",
        description="基于 CART 决策树的最优分箱",
        icon="🌳",
        inputs=[PortSchema(name="df", type="DataFrame", required=True)],
        outputs=[
            PortSchema(name="binner", type="BinnerArtifact", description="训练好的分箱器"),
            PortSchema(
                name="binned_df",
                type="DataFrame",
                description="分箱后的 DataFrame（含分箱索引列）",
            ),
        ],
        params=[
            ParamSpec(name="feature", type="str", label="特征列名", required=True),
            ParamSpec(name="target", type="str", label="目标列名", required=True),
            ParamSpec(name="min_n_bins", type="int", label="最少分箱数", default=2, min=2, max=10),
            ParamSpec(
                name="max_n_bins",
                type="int",
                label="最多分箱数",
                default=5,
                min=2,
                max=20,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=300,
        estimated_duration_sec=30,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        try:
            from hscredit.core.binning import OptimalBinning
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.binning.OptimalBinning 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        df = inputs["df"]
        feature = params["feature"]
        target = params["target"]
        if feature not in df.columns:
            raise ValidationError(
                f"特征列 {feature} 不存在",
                details={"node_type": self.contract.node_type, "feature": feature},
            )
        if target not in df.columns:
            raise ValidationError(
                f"目标列 {target} 不存在",
                details={"node_type": self.contract.node_type, "target": target},
            )

        min_n_bins = int(params.get("min_n_bins", 2))
        max_n_bins = int(params.get("max_n_bins", 5))
        if max_n_bins < min_n_bins:
            max_n_bins = min_n_bins

        binner = OptimalBinning(
            target=target,
            method="cart",
            min_n_bins=min_n_bins,
            max_n_bins=max_n_bins,
        )
        try:
            # fit 期望 1D X；传 values.ravel() 避免 (n,1) shape
            binner.fit(df[feature].values.ravel(), df[target].values.ravel())
        except Exception as e:
            raise ValidationError(
                f"CART 分箱 fit 失败: {e}",
                details={
                    "node_type": self.contract.node_type,
                    "feature": feature,
                    "method": "cart",
                },
            ) from e

        try:
            binned_series = binner.transform(df[feature], metric="indices")
        except Exception:
            binned_series = binner.transform(df[feature])

        binned_df = df.copy()
        binned_df[f"{feature}_bin"] = pd.Series(binned_series, index=df.index)
        # 与 optimal_binning_chi 保持一致：df 字段也带分箱列，确保汇聚场景正确
        return {"binner": binner, "binned_df": binned_df, "df": binned_df}
