"""特征选择节点族 — 6 种选择器 (Phase 6 B36).

封装 hscredit 的 6 种特征选择器:

- ``chi2_selector`` — 卡方统计量选择
- ``f_test_selector`` — F 检验选择
- ``rfe_selector`` — 递归特征消除
- ``psi_selector`` — PSI 跨期稳定性选择
- ``stability_selector`` — 稳定性感知选择 (IV+PSI 综合)
- ``stepwise_selector`` — 逐步回归选择

输入: ``df`` (DataFrame)
输出: ``selector`` (SelectorArtifact) + ``selected_df`` (DataFrame, 筛选后的列)

PSI 与 Stability 节点需要时间/分组列以计算跨期变化,
因此还接受 ``time_col`` 或 ``period_col`` 等额外参数.
"""

from __future__ import annotations

from typing import Any

from hscredit_studio.core.exceptions import (
    DependencyError,
    FeatureNotFoundError,
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


def _make_selector_contract(
    node_type: str,
    name: str,
    description: str,
    icon: str,
    extra_params: list[ParamSpec] | None = None,
) -> NodeContract:
    params: list[ParamSpec] = [target_param()]
    params.append(
        ParamSpec(
            name="threshold",
            type="float",
            label="筛选阈值 (随选择器语义不同)",
            default=0.02,
            min=0.0,
            max=1.0,
            advanced=True,
        )
    )
    params.append(
        ParamSpec(
            name="exclude",
            type="list",
            label="强制排除列 (如 ID/时间列)",
            default=[],
            advanced=True,
        )
    )
    if extra_params:
        params.extend(extra_params)
    return NodeContract(
        node_type=node_type,
        category="特征筛选",
        name=name,
        description=description,
        icon=icon,
        inputs=[
            PortSchema(
                name="df",
                type="DataFrame",
                required=True,
                aliases=["woe_df", "selected_df", "binned_df", "encoded_df"],
            ),
        ],
        outputs=[
            PortSchema(name="selector", type="SelectorArtifact", description="训练好的选择器"),
            PortSchema(name="selected_df", type="DataFrame", description="筛选后的 DataFrame"),
            PortSchema(name="removed_features", type="JSON", description="被剔除的特征列表"),
        ],
        params=params,
        cache=CacheConfig(),
        timeout_sec=300,
        estimated_duration_sec=30,
        tags=["feature_selection"],
        version="1.0.0",
    )


def _build_selector_run(class_name: str, class_path: str):
    """生成选择器 run() 闭包."""
    def run(self, inputs, params):
        try:
            import importlib

            mod = importlib.import_module(class_path)
            selector_cls = getattr(mod, class_name)
        except (ImportError, AttributeError) as e:
            raise DependencyError(
                f"{class_path}.{class_name} 不可用: {e}",
                details={"node_type": self.contract.node_type, "selector_class": class_name},
            ) from e

        df = resolve_dataframe_input(
            inputs,
            self.contract.node_type,
            aliases=("df", "woe_df", "selected_df", "binned_df", "encoded_df"),
        )
        target = params.get("target")
        if target and target not in df.columns:
            raise FeatureNotFoundError(
                f"目标列 {target} 不存在",
                details={"node_type": self.contract.node_type, "target": target},
            )

        exclude = params.get("exclude") or []
        threshold = float(params.get("threshold", 0.02))

        kwargs: dict[str, Any] = {
            "target": target or "target",
            "threshold": threshold,
            "exclude": exclude or None,
        }
        # 透传其它参数 (如 RFE 的 n_features_to_select, stepwise 的 direction)
        for key, value in params.items():
            if key in ("target", "threshold", "exclude"):
                continue
            kwargs[key] = value

        try:
            selector = selector_cls(**kwargs)
        except TypeError as e:
            raise ValidationError(
                f"构造选择器 {class_name} 失败: {e}",
                details={"node_type": self.contract.node_type, "kwargs": kwargs},
            ) from e

        try:
            selector.fit(df)
        except Exception as e:
            raise ValidationError(
                f"{class_name} fit 失败: {e}",
                details={"node_type": self.contract.node_type, "kwargs": kwargs},
            ) from e

        try:
            selected_df = selector.transform(df)
        except Exception as e:
            raise ValidationError(
                f"{class_name} transform 失败: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        removed = list(getattr(selector, "removed_features_", []))
        return {
            "selector": selector,
            "selected_df": selected_df,
            "removed_features": removed,
        }

    return run


def _make_selector_node(
    node_type: str,
    class_path: str,
    class_name: str,
    display_name: str,
    description: str,
    icon: str,
    extra_params: list[ParamSpec] | None = None,
):
    node_contract = _make_selector_contract(
        node_type=node_type,
        name=display_name,
        description=description,
        icon=icon,
        extra_params=extra_params,
    )

    @register_node
    class _GeneratedNode(BaseNode):
        contract = node_contract

    setattr(_GeneratedNode, "run", _build_selector_run(class_name, class_path))
    _GeneratedNode.__name__ = f"{node_type.replace('_', ' ').title().replace(' ', '')}Node"
    return _GeneratedNode


# ===== 6 个特征选择节点 =====

Chi2SelectorNode = _make_selector_node(
    node_type="chi2_selector",
    class_path="hscredit.core.selectors",
    class_name="Chi2Selector",
    display_name="卡方选择",
    description="按卡方统计量 p-value 选择特征 (chi2_selector)",
    icon="✖️",
    extra_params=[
        ParamSpec(
            name="k",
            type="select",
            label="选择 K 个特征 ('all' = 按 threshold)",
            default="all",
            choices=[
                ParamChoice(label="all (按阈值)", value="all"),
                ParamChoice(label="top 10", value=10),
                ParamChoice(label="top 20", value=20),
            ],
            advanced=True,
        ),
    ],
)

FTestSelectorNode = _make_selector_node(
    node_type="f_test_selector",
    class_path="hscredit.core.selectors",
    class_name="FTestSelector",
    display_name="F 检验选择",
    description="按 ANOVA F 统计量选择特征 (f_test_selector)",
    icon="🧪",
)

RFESelectorNode = _make_selector_node(
    node_type="rfe_selector",
    class_path="hscredit.core.selectors",
    class_name="RFESelector",
    display_name="递归特征消除 (RFE)",
    description="递归特征消除 (RFE), 默认 LogisticRegression 作为 estimator",
    icon="🔁",
    extra_params=[
        ParamSpec(
            name="n_features_to_select",
            type="int",
            label="保留特征数",
            default=10,
            min=1,
            max=1000,
        ),
        ParamSpec(
            name="step",
            type="int",
            label="每轮剔除特征数",
            default=1,
            min=1,
            max=100,
            advanced=True,
        ),
    ],
)

PSISelectorNode = _make_selector_node(
    node_type="psi_selector",
    class_path="hscredit.core.selectors",
    class_name="PSISelector",
    display_name="PSI 稳定性选择",
    description="按 PSI 阈值筛选跨期稳定特征 (psi_selector)",
    icon="📆",
    extra_params=[
        ParamSpec(
            name="period_col",
            type="str",
            label="时间/分组列名",
            description="用于切分 train/test 周期 (必须存在于 df)",
            required=False,
        ),
        ParamSpec(
            name="n_bins",
            type="int",
            label="PSI 计算分箱数",
            default=10,
            min=2,
            max=50,
            advanced=True,
        ),
    ],
)

StabilitySelectorNode = _make_selector_node(
    node_type="stability_selector",
    class_path="hscredit.core.selectors",
    class_name="StabilityAwareSelector",
    display_name="稳定性感知选择",
    description="综合 IV+PSI+综合评分 筛选, 适合评分卡建模",
    icon="⚖️",
    extra_params=[
        ParamSpec(
            name="iv_threshold",
            type="float",
            label="IV 阈值",
            default=0.02,
            min=0.0,
            max=1.0,
            advanced=True,
        ),
        ParamSpec(
            name="psi_threshold",
            type="float",
            label="PSI 阈值",
            default=0.1,
            min=0.0,
            max=1.0,
            advanced=True,
        ),
        ParamSpec(
            name="score_threshold",
            type="float",
            label="综合评分阈值",
            default=0.0,
            advanced=True,
        ),
    ],
)

StepwiseSelectorNode = _make_selector_node(
    node_type="stepwise_selector",
    class_path="hscredit.core.selectors",
    class_name="StepwiseSelector",
    display_name="逐步回归选择",
    description="逐步回归 (前向/后向/双向) 选择特征 (stepwise_selector)",
    icon="📊",
    extra_params=[
        ParamSpec(
            name="direction",
            type="select",
            label="逐步方向",
            default="forward",
            choices=[
                ParamChoice(label="forward (前向)", value="forward"),
                ParamChoice(label="backward (后向)", value="backward"),
                ParamChoice(label="both (双向)", value="both"),
            ],
        ),
        ParamSpec(
            name="criterion",
            type="select",
            label="判停准则",
            default="aic",
            choices=[
                ParamChoice(label="aic", value="aic"),
                ParamChoice(label="bic", value="bic"),
                ParamChoice(label="pvalue", value="pvalue"),
            ],
            advanced=True,
        ),
    ],
)


__all__ = [
    "Chi2SelectorNode",
    "FTestSelectorNode",
    "PSISelectorNode",
    "RFESelectorNode",
    "StabilitySelectorNode",
    "StepwiseSelectorNode",
]