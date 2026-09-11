"""规则引擎节点 — 3 个节点 (Phase 6 B36 阶段 2.2).

封装 hscredit.core.rules 与 hscredit.core.models.rules:

- ``rule_extract`` — :class:`Rule` 单条规则 (pandas eval 表达式)
- ``rule_classifier`` — :class:`RulesClassifier` 规则分类器 (AND/OR 组合)
- ``rule_flow`` — :class:`RuleFlow` 规则决策流 (serial/parallel)
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hscredit_studio.core.exceptions import (
    DependencyError,
    FeatureNotFoundError,
    ValidationError,
)
from hscredit_studio.nodes._common import resolve_dataframe_input
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.nodes.registry import register_node
from hscredit_studio.schemas.node_contract import (
    CacheConfig,
    NodeContract,
    ParamChoice,
    ParamSpec,
    PortSchema,
)


# ===== 1. 单条规则 =====


@register_node
class RuleExtractNode(BaseNode):
    """单条规则定义与评估.

    输入: 规则表达式 (pandas eval 语法, 如 ``age > 18 and income < 5000``)
    输出: 命中掩码 + 命中统计
    """

    contract = NodeContract(
        node_type="rule_extract",
        category="评分卡与规则",
        name="规则提取",
        description="单条规则定义与命中评估 (pandas eval 语法)",
        icon="📜",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["selected_df", "woe_df", "encoded_df"])],
        outputs=[
            PortSchema(name="rule", type="RuleArtifact", description="训练好的 Rule 对象"),
            PortSchema(name="mask", type="DataFrame", description="命中掩码 (1=命中, 0=未命中)"),
            PortSchema(name="df", type="DataFrame", description="= inputs.df (透传, 含 hit 列)"),
            PortSchema(name="stats", type="JSON", description="命中统计 (count/total/rate)"),
        ],
        params=[
            ParamSpec(
                name="expr",
                type="str",
                label="规则表达式 (pandas eval 语法)",
                required=True,
                placeholder="age > 18 and income < 5000",
            ),
            ParamSpec(name="name", type="str", label="规则名称 (可选)", default=""),
            ParamSpec(name="description", type="str", label="规则描述 (可选)", default="", advanced=True),
        ],
        cache=CacheConfig(),
        timeout_sec=60,
        estimated_duration_sec=2,
        tags=["rules"],
        version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.rules import Rule
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.rules.Rule 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        expr = params.get("expr")
        if not expr:
            raise ValidationError(
                f"节点 {self.contract.node_type} 需要 expr 参数",
                details={"node_type": self.contract.node_type},
            )

        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "selected_df", "woe_df", "encoded_df"))
        rule = Rule(
            expr=expr,
            name=params.get("name") or expr,
            description=params.get("description", ""),
        )
        try:
            mask = rule.predict(df).astype(int)
        except Exception as e:
            raise ValidationError(
                f"规则评估失败: {e}",
                details={"node_type": self.contract.node_type, "expr": expr},
            ) from e

        df_out = df.copy()
        df_out["hit"] = mask.values
        stats = {
            "count": int(mask.sum()),
            "total": int(len(mask)),
            "rate": float(mask.mean()),
            "expr": expr,
            "name": rule.name,
        }
        return {"rule": rule, "mask": pd.DataFrame({"hit": mask}), "df": df_out, "stats": stats}


# ===== 2. 规则分类器 =====


@register_node
class RuleClassifierNode(BaseNode):
    """规则集分类器 (RulesClassifier).

    接收多条 :class:`Rule` 或 :class:`RuleSet`, 通过 AND/OR 组合预测.
    """

    contract = NodeContract(
        node_type="rule_classifier",
        category="评分卡与规则",
        name="规则分类器",
        description="多条规则组合分类 (AND/OR), 输出 0/1 预测与命中权重",
        icon="📚",
        inputs=[
            PortSchema(name="df", type="DataFrame", required=True, aliases=["selected_df", "woe_df", "encoded_df"]),
            PortSchema(
                name="rule",
                type="RuleArtifact",
                required=False,
                multi=True,
                description="上游规则节点输出 (可多个)",
            ),
        ],
        outputs=[
            PortSchema(name="classifier", type="RuleArtifact", description="训练好的 RulesClassifier"),
            PortSchema(name="predictions", type="DataFrame", description="预测结果 (含 prediction 列)"),
        ],
        params=[
            ParamSpec(
                name="logic",
                type="select",
                label="规则组合逻辑",
                default="or",
                choices=[
                    ParamChoice(label="or (任一命中即 1)", value="or"),
                    ParamChoice(label="and (全部命中才 1)", value="and"),
                ],
            ),
            ParamSpec(
                name="output_mode",
                type="select",
                label="输出模式",
                default="final",
                choices=[
                    ParamChoice(label="final (最终 0/1)", value="final"),
                    ParamChoice(label="individual (每条规则的命中)", value="individual"),
                    ParamChoice(label="both (final + individual)", value="both"),
                    ParamChoice(label="reason (原因码)", value="reason"),
                ],
            ),
            ParamSpec(name="threshold", type="float", label="阈值", default=0.5, min=0.0, max=1.0, advanced=True),
        ],
        cache=CacheConfig(),
        timeout_sec=60,
        estimated_duration_sec=2,
        tags=["rules", "classifier"],
        version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.models.rules import RulesClassifier
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.models.rules.RulesClassifier 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "selected_df", "woe_df", "encoded_df"))
        rules = inputs.get("rule")
        if rules is None:
            raise ValidationError(
                "缺少必需输入端口 rule",
                details={"node_type": self.contract.node_type, "available_inputs": list(inputs.keys())},
            )
        # executor 可能把 multi 端口合并成 list
        if isinstance(rules, list):
            rules = list(rules)
        else:
            rules = [rules]

        try:
            classifier = RulesClassifier(
                rules=rules,
                logic=params.get("logic", "or"),
                output_mode=params.get("output_mode", "final"),
                threshold=float(params.get("threshold", 0.5)),
            )
            classifier.fit(df)
            preds = classifier.predict(df)
        except Exception as e:
            raise ValidationError(
                f"RulesClassifier 训练/预测失败: {e}",
                details={"node_type": self.contract.node_type, "n_rules": len(rules)},
            ) from e

        pred_df = pd.DataFrame({"prediction": preds})
        return {"classifier": classifier, "predictions": pred_df}


# ===== 3. 规则决策流 =====


@register_node
class RuleFlowNode(BaseNode):
    """规则决策流 (RuleFlow)."""

    contract = NodeContract(
        node_type="rule_flow",
        category="评分卡与规则",
        name="规则决策流",
        description="规则决策流 (serial/parallel), 用于策略串联",
        icon="🌊",
        inputs=[
            PortSchema(name="df", type="DataFrame", required=True, aliases=["selected_df", "woe_df", "encoded_df"]),
            PortSchema(
                name="rule",
                type="RuleArtifact",
                required=False,
                multi=True,
                description="上游规则节点输出 (可多个, 按顺序串联)",
            ),
        ],
        outputs=[
            PortSchema(name="flow", type="RuleArtifact", description="训练好的 RuleFlow"),
            PortSchema(name="predictions", type="DataFrame", description="流式预测结果"),
        ],
        params=[
            ParamSpec(
                name="mode",
                type="select",
                label="执行模式",
                default="serial",
                choices=[
                    ParamChoice(label="serial (顺序, 短路)", value="serial"),
                    ParamChoice(label="parallel (并行, 全部评估)", value="parallel"),
                ],
            ),
            ParamSpec(name="name", type="str", label="决策流名称", default="RuleFlow", advanced=True),
        ],
        cache=CacheConfig(),
        timeout_sec=60,
        estimated_duration_sec=2,
        tags=["rules", "flow"],
        version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.rules import RuleFlow
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.rules.RuleFlow 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "selected_df", "woe_df", "encoded_df"))
        rules = inputs.get("rule")
        if rules is None:
            raise ValidationError(
                "缺少必需输入端口 rule",
                details={"node_type": self.contract.node_type, "available_inputs": list(inputs.keys())},
            )
        if isinstance(rules, list):
            rules = list(rules)
        else:
            rules = [rules]

        try:
            flow = RuleFlow(
                rules=rules,
                mode=params.get("mode", "serial"),
                name=params.get("name", "RuleFlow"),
            )
            flow.fit(df)
            preds = flow.predict(df)
        except Exception as e:
            raise ValidationError(
                f"RuleFlow 训练/预测失败: {e}",
                details={"node_type": self.contract.node_type, "n_rules": len(rules)},
            ) from e

        pred_df = pd.DataFrame({"prediction": preds})
        return {"flow": flow, "predictions": pred_df}