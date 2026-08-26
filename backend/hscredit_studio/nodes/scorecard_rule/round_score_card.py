"""圆整评分卡 — 对 ScoreCard 的分数做整数化（降级实现）.

**实现说明**

hscredit 库的 ``RoundScoreCard`` 类
(``hscredit/core/models/scorecard/round.py``) 当前尚未实现。
本节点作为临时替代: 调用标准 :class:`ScoreCard.scorecard_points` 获取分箱分数表,
把分数列四舍五入到指定 ``decimal`` 位, 可选截断到 ``[min_score, max_score]``。

**降级实现细节（Phase 2 待切换）**

- 不修改 ScoreCard 对象本身, 仅在 ``score_points`` 上做整数化。
- ``score_card_rounded`` 输出原始 ScoreCard（仅 score 列经过整数化）,
  后续 ``model_report`` 节点仍可消费。
- 一旦 hscredit 补齐 ``RoundScoreCard``, 改用其 ``fit_transform`` 接口。
"""
from __future__ import annotations

from typing import Any

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
    ParamSpec,
    PortSchema,
)


_SCORE_COLUMN_HINTS = ("score", "分", "对应分数")


def _find_score_column(columns: list[str]) -> str | None:
    """寻找最像分数列的字段名.

    兼容 ``对应分数`` / ``分数`` / ``score`` / ``Score`` 等多种命名。
    """
    lowered = [str(c).lower() for c in columns]
    # 1) 优先匹配 "对应分数" 等中文 score 字段
    for col in columns:
        lc = str(col).lower()
        if "对应分数" in str(col) or lc == "score" or "score_value" in lc:
            return col
    # 2) 含 "分" 或 "score" 的兜底匹配
    for col, lc in zip(columns, lowered):
        if "分" in str(col) or "score" in lc:
            return col
    return None


@register_node
class RoundScoreCardNode(BaseNode):
    """圆整评分卡 — 对 ScoreCard 的分数做整数化."""

    contract = NodeContract(
        node_type="round_score_card",
        category="评分卡与规则",
        name="圆整评分卡",
        description="对标准评分卡的分数四舍五入到整数（降级实现）",
        icon="🔢",
        inputs=[
            PortSchema(
                name="score_card",
                type="ScorecardArtifact",
                required=True,
                description="上游标准评分卡对象",
            ),
        ],
        outputs=[
            PortSchema(
                name="score_points",
                type="DataFrame",
                description="圆整后的评分卡分箱分数表",
            ),
            PortSchema(
                name="score_card_rounded",
                type="ScorecardArtifact",
                description="圆整后的 ScoreCard 对象（仅 score 列整数化）",
            ),
        ],
        params=[
            ParamSpec(
                name="decimal",
                type="int",
                label="保留小数位（0=整数）",
                default=0,
                min=0,
                max=4,
            ),
            ParamSpec(
                name="min_score",
                type="int",
                label="最低分下限",
                default=0,
                advanced=True,
            ),
            ParamSpec(
                name="max_score",
                type="int",
                label="最高分上限",
                default=1000,
                advanced=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=120,
        estimated_duration_sec=5,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        sc = inputs.get("score_card")
        if sc is None:
            raise FeatureNotFoundError(
                "未传入 score_card",
                details={"node_type": self.contract.node_type},
            )

        if not hasattr(sc, "scorecard_points"):
            raise DependencyError(
                "传入对象没有 scorecard_points 方法, 不是 ScoreCard 实例",
                details={"node_type": self.contract.node_type, "type": type(sc).__name__},
            )

        decimal = int(params.get("decimal", 0))
        min_score = params.get("min_score")
        max_score = params.get("max_score")

        try:
            points_df = sc.scorecard_points().copy()
        except Exception as e:
            raise ValidationError(
                f"读取评分卡分箱分数表失败: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        score_col = _find_score_column(list(points_df.columns))
        if score_col is None:
            raise FeatureNotFoundError(
                "score_card 中未找到分数列（尝试 '对应分数'/'分数'/'score'）",
                details={"node_type": self.contract.node_type, "columns": list(points_df.columns)},
            )

        # 四舍五入到指定小数位
        try:
            points_df[score_col] = points_df[score_col].astype(float).round(decimal)
            if decimal == 0:
                points_df[score_col] = points_df[score_col].astype(int)
        except (TypeError, ValueError) as e:
            raise ValidationError(
                f"分数列整数化失败: {e}",
                details={"node_type": self.contract.node_type, "score_col": score_col},
            ) from e

        # 截断到 [min_score, max_score]
        try:
            if min_score is not None or max_score is not None:
                lower = min_score if min_score is not None else -float("inf")
                upper = max_score if max_score is not None else float("inf")
                points_df[score_col] = points_df[score_col].clip(lower=lower, upper=upper)
        except (TypeError, ValueError) as e:
            raise ValidationError(
                f"分数截断失败: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        return {"score_points": points_df, "score_card_rounded": sc}
