"""单方法分箱节点族 — 为前端按算法分类展示提供独立 node_type.

为每种主流分箱算法暴露一个独立节点:

- ``uniform_binning`` — 等宽分箱
- ``quantile_binning`` — 等频分箱
- ``cart_binning`` — CART 分箱 (optbinning 风格)
- ``monotonic_binning`` — 单调约束分箱 (U 型/倒 U/凸/凹)
- ``best_iv_binning`` — 最优 IV 分箱
- ``best_ks_binning`` — 最优 KS 分箱

每个节点都是 :class:`_SingleMethodBinningNode` 的子类, 通过类变量
``METHOD`` 指定底层 ``OptimalBinning`` 的 method 字符串.
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


class _SingleMethodBinningNode(BaseNode):
    """单方法分箱节点基类.

    子类覆盖 :attr:`METHOD` 与 :attr:`NODE_TYPE` 即可复用全部业务逻辑.
    基类不定义 ``contract`` (避免触发 NodeContract 的严格校验),
    由 :func:`_make_node` 在子类化时构造并赋值.
    """

    METHOD: str = ""  # 子类覆盖
    NODE_TYPE: str = ""  # 子类覆盖
    DISPLAY_NAME: str = ""
    DESCRIPTION: str = ""
    ICON: str = "📐"

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

        min_n_bins = int(params.get("min_n_bins", 2))
        max_n_bins = int(params.get("max_n_bins", 5))
        if max_n_bins < min_n_bins:
            max_n_bins = min_n_bins

        kwargs: dict[str, Any] = {
            "target": target,
            "method": self.METHOD,
            "min_n_bins": min_n_bins,
            "max_n_bins": max_n_bins,
        }
        # 单调分箱: monotonic 是关键参数
        if self.METHOD == "monotonic":
            monotonic = params.get("monotonic", "asc")
            kwargs["monotonic"] = monotonic

        binner = OptimalBinning(**kwargs)
        try:
            binner.fit(df[feature].values.ravel(), df[target].values.ravel())
        except Exception as e:
            raise ValidationError(
                f"{self.METHOD} 分箱 fit 失败: {e}",
                details={
                    "node_type": self.contract.node_type,
                    "feature": feature,
                    "method": self.METHOD,
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


def _make_node(
    node_type: str, method: str, display_name: str, description: str, icon: str
) -> type[_SingleMethodBinningNode]:
    """为每种方法生成独立节点类 + 注册到全局表."""

    @register_node
    class _GeneratedNode(_SingleMethodBinningNode):
        contract = NodeContract(
            node_type=node_type,
            category="特征工程",
            name=display_name,
            description=description,
            icon=icon,
            inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["binned_df"])],
            outputs=[
                PortSchema(name="binner", type="BinnerArtifact"),
                PortSchema(name="binned_df", type="DataFrame"),
                PortSchema(name="df", type="DataFrame"),
            ],
            params=_build_params(method),
            cache=CacheConfig(),
            timeout_sec=300,
            estimated_duration_sec=30,
            tags=["binning", method],
            version="1.0.0",
        )
        METHOD = method
        NODE_TYPE = node_type
        DISPLAY_NAME = display_name
        DESCRIPTION = description
        ICON = icon

    _GeneratedNode.__name__ = f"{node_type.replace('_', ' ').title().replace(' ', '')}Node"
    return _GeneratedNode


def _build_params(method: str) -> list[ParamSpec]:
    """根据方法生成 ParamSpec 列表."""
    base = [
        ParamSpec(name="feature", type="str", label="特征列名", required=True),
        target_param(),
        ParamSpec(name="min_n_bins", type="int", label="最少分箱数", default=2, min=2, max=10),
        ParamSpec(
            name="max_n_bins",
            type="int",
            label="最多分箱数",
            default=5,
            min=2,
            max=20,
        ),
    ]
    if method == "monotonic":
        base.append(
            ParamSpec(
                name="monotonic",
                type="select",
                label="单调约束",
                default="asc",
                choices=[
                    ParamChoice(label="asc (升序, 单调递增)", value="asc"),
                    ParamChoice(label="desc (降序, 单调递减)", value="desc"),
                    ParamChoice(label="u (U 型)", value="u"),
                    ParamChoice(label="inverted_u (倒 U 型)", value="inverted_u"),
                    ParamChoice(label="convex (凸型)", value="convex"),
                    ParamChoice(label="concave (凹型)", value="concave"),
                ],
            )
        )
    return base


# 注册 6 种主流分箱节点
UniformBinningNode = _make_node(
    node_type="uniform_binning",
    method="uniform",
    display_name="等宽分箱",
    description="将特征按值域等宽切分为 N 箱",
    icon="📏",
)
QuantileBinningNode = _make_node(
    node_type="quantile_binning",
    method="quantile",
    display_name="等频分箱",
    description="按样本量等频切分, 每箱样本数相近",
    icon="📊",
)
CartBinningNode = _make_node(
    node_type="cart_binning",
    method="cart",
    display_name="CART 分箱",
    description="基于决策树的最优分箱 (optbinning 风格)",
    icon="🌳",
)
MonotonicBinningNode = _make_node(
    node_type="monotonic_binning",
    method="monotonic",
    display_name="单调分箱",
    description="单调约束分箱 (U/倒U/凸/凹), 适合评分卡",
    icon="📈",
)
BestIVBinningNode = _make_node(
    node_type="best_iv_binning",
    method="best_iv",
    display_name="最优 IV 分箱",
    description="最大化 IV 的分箱",
    icon="🎯",
)
BestKSBinningNode = _make_node(
    node_type="best_ks_binning",
    method="best_ks",
    display_name="最优 KS 分箱",
    description="最大化 KS 统计量的分箱",
    icon="🎪",
)


__all__ = [
    "BestIVBinningNode",
    "BestKSBinningNode",
    "CartBinningNode",
    "MonotonicBinningNode",
    "QuantileBinningNode",
    "UniformBinningNode",
    "_SingleMethodBinningNode",
]