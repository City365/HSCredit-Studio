"""扩展评分卡节点 — 2 个新节点 (Phase 6 B36).

封装 hscredit.scorecard 子包:

- ``model_scorecard`` — :class:`ProbabilityScoreCard`, 任意 ``predict_proba`` 模型 → 评分
- ``score_transformer`` — :class:`ScoreTransformer`, 概率 ↔ 评分统一转换接口
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hscredit_studio.core.exceptions import (
    DependencyError,
    FeatureNotFoundError,
    ValidationError,
)
from hscredit_studio.nodes._common import coerce_features_param, resolve_dataframe_input, target_param
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.nodes.registry import register_node
from hscredit_studio.schemas.node_contract import (
    CacheConfig,
    NodeContract,
    ParamChoice,
    ParamSpec,
    PortSchema,
)


# ===== model_scorecard =====


@register_node
class ModelScoreCardNode(BaseNode):
    """通用模型 → 评分卡 (ProbabilityScoreCard).

    接收任意 :class:`predict_proba` 模型 (如 XGBoost/LightGBM/Logistic),
    转换为 ProbabilityScoreCard, 支持 4 种评分方法:

    - standard: 标准 (PDO/odds 公式)
    - linear: 线性
    - quantile: 分位数
    - boxcox: Box-Cox 幂变换
    """

    contract = NodeContract(
        node_type="model_scorecard",
        category="评分卡与规则",
        name="模型评分卡",
        description="把任意 predict_proba 模型转换为评分卡 (ProbabilityScoreCard)",
        icon="💳",
        inputs=[
            PortSchema(
                name="df",
                type="DataFrame",
                required=True,
                aliases=["woe_df", "selected_df", "binned_df", "encoded_df"],
            ),
            PortSchema(
                name="model",
                type="ModelArtifact",
                required=True,
                aliases=["logistic_model", "lr_model"],
                description="上游模型 (XGBoost/LightGBM/Logistic 等)",
            ),
        ],
        outputs=[
            PortSchema(
                name="score_card",
                type="ScorecardArtifact",
                description="训练好的 ProbabilityScoreCard",
            ),
            PortSchema(
                name="scores",
                type="DataFrame",
                description="样本评分结果 (含 score 列)",
            ),
        ],
        params=[
            target_param(),
            ParamSpec(name="features", type="list", label="特征列表", required=True),
            ParamSpec(
                name="method",
                type="select",
                label="评分方法",
                default="standard",
                choices=[
                    ParamChoice(label="standard (标准 PDO/odds)", value="standard"),
                    ParamChoice(label="linear (线性)", value="linear"),
                    ParamChoice(label="quantile (分位数)", value="quantile"),
                    ParamChoice(label="boxcox (Box-Cox 幂变换)", value="boxcox"),
                ],
            ),
            ParamSpec(name="base_score", type="int", label="基础分", default=600, min=0, max=2000, advanced=True),
            ParamSpec(name="pdo", type="float", label="PDO (Points to Double Odds)", default=20.0, advanced=True),
            ParamSpec(name="base_odds", type="float", label="基础 Odds (坏/好)", default=0.05, advanced=True),
            ParamSpec(
                name="direction",
                type="select",
                label="评分方向",
                default="descending",
                choices=[
                    ParamChoice(label="descending (概率低 → 分数高)", value="descending"),
                    ParamChoice(label="ascending (概率高 → 分数高)", value="ascending"),
                ],
                advanced=True,
            ),
            ParamSpec(name="decimal", type="int", label="小数位数", default=0, min=0, max=4, advanced=True),
        ],
        cache=CacheConfig(),
        timeout_sec=300,
        estimated_duration_sec=15,
        tags=["scorecard"],
        version="1.0.0",
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        try:
            from hscredit.core.models.scorecard import ProbabilityScoreCard
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.models.scorecard.ProbabilityScoreCard 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        df = resolve_dataframe_input(
            inputs,
            self.contract.node_type,
            aliases=("df", "woe_df", "selected_df", "binned_df", "encoded_df"),
        )
        target = params.get("target")
        if not target:
            raise ValidationError(
                f"节点 {self.contract.node_type} 需要 target 参数",
                details={"node_type": self.contract.node_type},
            )
        if target not in df.columns:
            raise FeatureNotFoundError(
                f"目标列 {target} 不存在",
                details={"node_type": self.contract.node_type, "target": target},
            )
        features = coerce_features_param(params.get("features"), list(df.columns), self.contract.node_type)
        model = inputs.get("model")
        if model is None:
            raise ValidationError(
                "缺少必需输入端口 model",
                details={"node_type": self.contract.node_type, "available_inputs": list(inputs.keys())},
            )

        card = ProbabilityScoreCard(
            model=model,
            method=params.get("method", "standard"),
            base_score=int(params.get("base_score", 600)),
            pdo=float(params.get("pdo", 20.0)),
            base_odds=float(params.get("base_odds", 0.05)),
            direction=params.get("direction", "descending"),
            decimal=int(params.get("decimal", 0)),
            target=target,
        )
        try:
            card.fit(df[features], df[target])
        except Exception as e:
            raise ValidationError(
                f"ProbabilityScoreCard.fit 失败: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        try:
            scores = card.predict(df[features])
        except Exception as e:
            raise ValidationError(
                f"ProbabilityScoreCard.predict 失败: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        scores_df = pd.DataFrame({"score": scores})
        scores_df[target] = df[target].values
        return {"score_card": card, "scores": scores_df}


# ===== score_transformer =====


@register_node
class ScoreTransformerNode(BaseNode):
    """评分转换器 — 概率 ↔ 评分统一接口.

    4 种评分转换方法:

    - standard: 标准 (PDO/odds)
    - linear: 线性
    - quantile: 分位数
    - boxcox: Box-Cox 幂变换
    """

    contract = NodeContract(
        node_type="score_transformer",
        category="评分卡与规则",
        name="评分转换器",
        description="ScoreTransformer — 概率与评分之间的转换工具",
        icon="🔄",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["scores", "score_df"])],
        outputs=[
            PortSchema(name="transformer", type="ScorecardArtifact", description="训练好的转换器"),
            PortSchema(
                name="converted_df",
                type="DataFrame",
                description="转换后的 DataFrame (含 score 列)",
            ),
        ],
        params=[
            ParamSpec(name="score_col", type="str", label="概率/分数列名", default="probability"),
            ParamSpec(
                name="method",
                type="select",
                label="转换方法",
                default="standard",
                choices=[
                    ParamChoice(label="standard", value="standard"),
                    ParamChoice(label="linear", value="linear"),
                    ParamChoice(label="quantile", value="quantile"),
                    ParamChoice(label="boxcox", value="boxcox"),
                ],
            ),
            ParamSpec(name="base_score", type="int", label="基础分", default=600, min=0, max=2000, advanced=True),
            ParamSpec(name="pdo", type="float", label="PDO", default=20.0, advanced=True),
            ParamSpec(name="base_odds", type="float", label="基础 Odds", default=0.05, advanced=True),
            ParamSpec(
                name="direction",
                type="select",
                label="方向",
                default="descending",
                choices=[
                    ParamChoice(label="descending", value="descending"),
                    ParamChoice(label="ascending", value="ascending"),
                ],
                advanced=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=300,
        estimated_duration_sec=10,
        tags=["scorecard", "transformer"],
        version="1.0.0",
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        try:
            from hscredit.core.models.scorecard import ScoreTransformer
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.models.scorecard.ScoreTransformer 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        df = resolve_dataframe_input(
            inputs,
            self.contract.node_type,
            aliases=("df", "scores", "score_df"),
        )
        score_col = params.get("score_col", "probability")
        if score_col not in df.columns:
            raise ValidationError(
                f"概率/分数列 {score_col} 不存在",
                details={
                    "node_type": self.contract.node_type,
                    "score_col": score_col,
                    "available": list(df.columns),
                },
            )

        transformer = ScoreTransformer(
            method=params.get("method", "standard"),
            base_score=int(params.get("base_score", 600)),
            pdo=float(params.get("pdo", 20.0)),
            base_odds=float(params.get("base_odds", 0.05)),
            direction=params.get("direction", "descending"),
        )
        try:
            probs = df[score_col].astype(float).values
            transformer.fit(probs)
            scores = transformer.transform(probs)
        except Exception as e:
            raise ValidationError(
                f"ScoreTransformer 转换失败: {e}",
                details={"node_type": self.contract.node_type, "method": params.get("method")},
            ) from e

        converted = df.copy()
        converted["score"] = scores
        return {"transformer": transformer, "converted_df": converted}