"""OptimalBinning 通用分箱节点 (Phase 6 B36 节点补齐).

通过 ``method`` 参数切换底层算法, 是分箱一站式入口.

对应 hscredit 的 ``OptimalBinning(method=...)``, 支持的方法:

- uniform / quantile / tree / chi (基础)
- best_ks / best_iv / mdlp / cart / monotonic (优化)
- kmeans / smooth / kernel_density / genetic (高级)
- best_lift / target_bad_rate / or_tools / cp_sat (专用)

由于前端需要按算法分类展示, 本节点统一走 ``optimal_binning`` node_type,
``method`` 暴露为 select 参数, 即可覆盖 17 种方法.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hscredit_studio.core.exceptions import (
    DependencyError,
    ValidationError,
)
from hscredit_studio.nodes._common import resolve_dataframe_input, target_param
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.nodes.registry import register_node
from hscredit_studio.schemas.node_contract import (
    CacheConfig,
    NodeContract,
    ParamChoice,
    ParamSpec,
    PortSchema,
)


# OptimalBinning.VALID_METHODS 同步 (从源码对齐)
_OPTIMAL_BINNING_METHODS = [
    "uniform",
    "quantile",
    "tree",
    "chi",
    "best_ks",
    "best_iv",
    "mdlp",
    "or_tools",
    "cp_sat",
    "cart",
    "kmeans",
    "monotonic",
    "genetic",
    "smooth",
    "kernel_density",
    "best_lift",
    "target_bad_rate",
]


@register_node
class OptimalBinningNode(BaseNode):
    """OptimalBinning 一站式分箱 (17 种方法)."""

    contract = NodeContract(
        node_type="optimal_binning",
        category="特征工程",
        name="最优分箱",
        description=(
            "通过 method 参数选择 17 种分箱算法之一 "
            "(uniform/quantile/tree/chi/best_ks/best_iv/mdlp/cart/"
            "monotonic/kmeans/smooth/kernel_density/genetic/best_lift/"
            "target_bad_rate/or_tools/cp_sat). "
            "底层调用 hscredit.core.binning.OptimalBinning."
        ),
        icon="📐",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["binned_df"])],
        outputs=[
            PortSchema(name="binner", type="BinnerArtifact", description="训练好的分箱器"),
            PortSchema(name="binned_df", type="DataFrame", description="含分箱列的 DataFrame"),
            PortSchema(name="df", type="DataFrame", description="= binned_df (别名, 便于下游直接引用)"),
        ],
        params=[
            ParamSpec(name="feature", type="str", label="特征列名", required=True),
            target_param(),
            ParamSpec(
                name="method",
                type="select",
                label="分箱方法",
                default="mdlp",
                choices=[ParamChoice(label=m, value=m) for m in _OPTIMAL_BINNING_METHODS],
                description="17 种分箱算法, 默认 MDLP (基于信息论)",
            ),
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
                name="monotonic",
                type="select",
                label="单调约束 (仅 monotonic 方法)",
                default="auto",
                choices=[
                    ParamChoice(label="auto (不约束)", value="auto"),
                    ParamChoice(label="asc (升序)", value="asc"),
                    ParamChoice(label="desc (降序)", value="desc"),
                    ParamChoice(label="u (U 型)", value="u"),
                    ParamChoice(label="inverted_u (倒 U)", value="inverted_u"),
                ],
                advanced=True,
            ),
            ParamSpec(
                name="min_bin_size",
                type="float",
                label="最小分箱占比 (0-1)",
                default=0.01,
                min=0.001,
                max=0.5,
                advanced=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=300,
        estimated_duration_sec=30,
        tags=["binning", "feature_engineering"],
        version="1.0.0",
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        try:
            from hscredit.core.binning import OptimalBinning
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.binning.OptimalBinning 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        df = resolve_dataframe_input(
            inputs, self.contract.node_type, aliases=("df", "binned_df", "selected_df", "woe_df")
        )
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

        method = params.get("method", "mdlp")
        min_n_bins = int(params.get("min_n_bins", 2))
        max_n_bins = int(params.get("max_n_bins", 5))
        if max_n_bins < min_n_bins:
            max_n_bins = min_n_bins

        monotonic = params.get("monotonic", "auto")
        if monotonic == "auto":
            monotonic_arg: Any = False
        else:
            monotonic_arg = monotonic

        min_bin_size = float(params.get("min_bin_size", 0.01))

        binner = OptimalBinning(
            target=target,
            method=method,
            min_n_bins=min_n_bins,
            max_n_bins=max_n_bins,
            monotonic=monotonic_arg,
            min_bin_size=min_bin_size,
        )
        try:
            binner.fit(df[feature].values.ravel(), df[target].values.ravel())
        except Exception as e:
            raise ValidationError(
                f"{method} 分箱 fit 失败: {e}",
                details={
                    "node_type": self.contract.node_type,
                    "feature": feature,
                    "method": method,
                },
            ) from e

        try:
            binned_series = binner.transform(df[feature].values.ravel(), metric="indices")
        except Exception:
            binned_series = binner.transform(df[feature].values.ravel())
        if hasattr(binned_series, "ndim") and binned_series.ndim == 2:
            binned_series = binned_series.iloc[:, 0]

        binned_df = df.copy()
        binned_df[f"{feature}_bin"] = pd.Series(binned_series, index=df.index)
        return {"binner": binner, "binned_df": binned_df, "df": binned_df}