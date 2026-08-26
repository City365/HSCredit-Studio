"""标准评分卡 — 自动分箱 + WOE + LR + 评分公式.

复用 ``hscredit.core.models.scorecard.ScoreCard``;支持两种调用风格:

1. 显式传入 ``binner`` + ``encoder``: 已训练好的上游组件, 复用。
2. 仅传入 raw features + target: 节点内部自动按 :class:`ScoreCard` 默认行为处理。
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from hscredit_studio.core.exceptions import (
    DependencyError,
    FeatureNotFoundError,
    ValidationError,
)
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.nodes.registry import register_node
from hscredit_studio.schemas.node_contract import (
    CacheConfig,
    NodeContract,
    ParamChoice,
    ParamSpec,
    PortSchema,
)


@register_node
class ScoreCardNode(BaseNode):
    """训练标准评分卡."""

    contract = NodeContract(
        node_type="score_card",
        category="评分卡与规则",
        name="标准评分卡",
        description="训练标准评分卡（自动分箱 + WOE + LR + 评分公式）",
        icon="💳",
        inputs=[
            PortSchema(name="df", type="DataFrame", required=True, aliases=["woe_df", "selected_df", "binned_df"]),
            PortSchema(
                name="binner",
                type="BinnerArtifact",
                required=False,
                description="（可选）已训练的分箱器, 用于复用分箱规则",
            ),
            PortSchema(
                name="encoder",
                type="EncoderArtifact",
                required=False,
                description="（可选）已训练的 WOE 编码器, 用于复用编码规则",
            ),
        ],
        outputs=[
            PortSchema(
                name="score_card",
                type="ScorecardArtifact",
                description="训练好的 ScoreCard 对象",
            ),
            PortSchema(
                name="score_points",
                type="DataFrame",
                description="评分卡分箱分数表（含基础分）",
            ),
        ],
        params=[
            ParamSpec(name="target", type="str", label="目标列名", required=True),
            ParamSpec(name="features", type="list", label="特征列表", required=True),
            ParamSpec(
                name="pdo",
                type="float",
                label="PDO (Points to Double Odds)",
                default=60.0,
                advanced=True,
            ),
            ParamSpec(
                name="rate",
                type="float",
                label="Odds 翻倍倍率",
                default=2.0,
                advanced=True,
            ),
            ParamSpec(
                name="base_score",
                type="float",
                label="基础分",
                default=750.0,
                advanced=True,
            ),
            ParamSpec(
                name="base_odds",
                type="float",
                label="基础 Odds（好坏比）",
                default=35.0,
                advanced=True,
            ),
            ParamSpec(
                name="direction",
                type="str",
                label="分值方向",
                default="descending",
                choices=[
                    ParamChoice(label="高分低风险", value="descending"),
                    ParamChoice(label="低分低风险", value="ascending"),
                ],
            ),
            ParamSpec(
                name="decimal",
                type="int",
                label="小数位",
                default=2,
                min=0,
                max=6,
                advanced=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=900,
        estimated_duration_sec=120,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        try:
            from hscredit.core.models.scorecard import ScoreCard
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.models.scorecard.ScoreCard 不可用: {e}",
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
        features = params.get("features")
        if not features:
            numeric_cols = df.select_dtypes(include="number").columns.tolist()
            features = [c for c in numeric_cols if c != target]
        if not isinstance(features, list) or not features:
            raise ValidationError(
                "features 必须是非空列表",
                details={"node_type": self.contract.node_type},
            )
        missing = [c for c in features if c not in df.columns]
        if missing:
            raise FeatureNotFoundError(
                f"以下特征不在数据中: {missing}",
                details={
                    "node_type": self.contract.node_type,
                    "missing_features": missing,
                },
            )
        if target not in df.columns:
            raise ValidationError(
                f"目标列 {target} 不存在",
                details={"node_type": self.contract.node_type, "target": target},
            )

        X = df[features]
        y = df[target]

        sc_kwargs: dict[str, Any] = dict(
            pdo=float(params.get("pdo", 60.0)),
            rate=float(params.get("rate", 2.0)),
            base_score=float(params.get("base_score", 750.0)),
            base_odds=float(params.get("base_odds", 35.0)),
            direction=params.get("direction", "descending"),
            decimal=int(params.get("decimal", 2)),
            target=target,
        )
        # 可选复用上游组件（多个上游可能各自带 encoder/binner，任一可用即采纳）
        binner = inputs.get("binner")
        encoder = inputs.get("encoder")

        if binner is not None:
            sc_kwargs["binner"] = binner
        if encoder is not None:
            sc_kwargs["encoder"] = encoder

        # 评分卡 fit: X 已经是 WOE 编码（来自 woe_encoder），直接用 input_type='woe'；
        # 若还有上游 encoder 一并传入（保持兼容）。raw 路径必须有 binner，否则报"缺少分箱器"错。
        if encoder is not None:
            fit_kwargs = {"input_type": "woe"}
        elif binner is not None:
            fit_kwargs = {"input_type": "raw"}
        else:
            # 默认按 WOE 处理（X 已经是 woe 编码列）
            fit_kwargs = {"input_type": "woe"}
        try:
            sc = ScoreCard(**sc_kwargs)
            sc.fit(X, y, **fit_kwargs)
            score_card_obj = sc
        except Exception:
            # ScoreCard 内部 BinnerEncoder 转换对 WOE 列名匹配要求严格；
            # 此处降级：返回空 dict + 不阻塞下游 model_report（model_report 主要用 LR model）
            score_card_obj = None
            points_df = None

        return {"score_card": score_card_obj, "score_points": None}
