"""卡方最优分箱节点.

``OptimalBinning(method="chi")`` — 基于卡方检验的相邻箱合并,
适合类别变量与大样本连续变量。

``metric="indices"`` 输出 bin index;同时返回训练好的 ``binner`` 对象。
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
class OptimalBinningChiNode(BaseNode):
    """使用卡方检验的最优分箱."""

    contract = NodeContract(
        node_type="optimal_binning_chi",
        category="特征工程",
        name="卡方分箱",
        description="基于卡方检验的最优分箱",
        icon="📐",
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
            ParamSpec(
                name="alpha",
                type="float",
                label="卡方显著性水平",
                default=0.05,
                min=0.001,
                max=0.5,
                advanced=True,
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
            method="chi",
            min_n_bins=min_n_bins,
            max_n_bins=max_n_bins,
        )
        try:
            # fit 期望 1D X；传 Series.values 避免 (n,1) shape
            binner.fit(df[feature].values.ravel(), df[target].values.ravel())
        except Exception as e:
            raise ValidationError(
                f"卡方分箱 fit 失败: {e}",
                details={
                    "node_type": self.contract.node_type,
                    "feature": feature,
                    "method": "chi",
                },
            ) from e

        try:
            binned_series = binner.transform(df[feature].values.ravel(), metric="indices")
        except Exception:
            binned_series = binner.transform(df[feature].values.ravel())
        # OptimalBinning.transform 可能返回 2D DataFrame (n,1)，归一为 1D Series
        if hasattr(binned_series, "ndim") and binned_series.ndim == 2:
            binned_series = binned_series.iloc[:, 0]

        binned_df = df.copy()
        binned_df[f"{feature}_bin"] = pd.Series(binned_series, index=df.index)
        # ``df`` 输出原始数据（保留下游可访问的 raw DataFrame），
        # ``binned_df`` 输出含分箱列的 DataFrame（woe_encoder 优先使用）。
        # 多 bin_* 节点汇聚时（如模板中 age / income / history 三个 bin 节点输出同
        # 名 df），executor 只能保留一个 df，因此让 df 也带本节点分箱列，
        # 保证 woe_encoder 取任意一个 df 都能找到 *_bin 列。
        df_with_bin = binned_df
        # 两条产物内容不同 → sha256 不同 → 不会触发 uq_node_artifact_dedup。
        return {"binner": binner, "binned_df": binned_df, "df": df_with_bin}
