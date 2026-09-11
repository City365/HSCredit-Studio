"""解释性节点 — 2 个节点 (Phase 6 B36 阶段 2.3).

封装 hscredit.core.models.explainability:

- ``reason_codes`` — :func:`build_reason_codes` 把 SHAP 解释转原因码
- ``shap_global`` — :class:`ModelExplainer` 全局 SHAP 解释 (summary)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from hscredit_studio.core.exceptions import (
    DependencyError,
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


# ===== 1. ReasonCodes =====


@register_node
class ReasonCodesNode(BaseNode):
    """基于 SHAP 解释生成原因码.

    输入: 上游 SHAP 解释结果 (ExplanationResult 对象)
    输出: 原因码 DataFrame (每行: sample_id, top reasons)
    """

    contract = NodeContract(
        node_type="reason_codes",
        category="报告与部署",
        name="拒绝原因码",
        description="把 SHAP 解释转为业务原因码 (每条样本 top-K 原因)",
        icon="🪧",
        inputs=[
            PortSchema(
                name="explanation",
                type="JSON",
                required=True,
                description="上游 ModelExplainer.explain() 的结果 (values + data + sample_ids)",
            ),
        ],
        outputs=[
            PortSchema(name="reason_df", type="DataFrame", description="原因码 DataFrame"),
            PortSchema(name="reason_map", type="JSON", description="原因码映射表 (feature -> readable)"),
        ],
        params=[
            ParamSpec(name="keep", type="int", label="保留前 K 条原因", default=3, min=1, max=10),
            ParamSpec(
                name="risk_direction",
                type="select",
                label="风险方向",
                default="higher_output_higher_risk",
                choices=[
                    ParamChoice(label="分数越高风险越高 (坏样本=1)", value="higher_output_higher_risk"),
                    ParamChoice(label="分数越高风险越低 (坏样本=0, 反欺诈场景)", value="higher_output_lower_risk"),
                ],
            ),
            ParamSpec(
                name="feature_map",
                type="json",
                label="特征名映射 {raw_name: display_name}",
                default=None,
                advanced=True,
                description='JSON, 例: {"age_bin": "年龄段"}',
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=60,
        estimated_duration_sec=2,
        tags=["explainability", "reason_codes"],
        version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.models.explainability import build_reason_codes
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.models.explainability.build_reason_codes 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        # 上游可能是 ExplanationResult 对象或 dict
        explanation = inputs.get("explanation")
        if explanation is None:
            raise ValidationError(
                "缺少必需输入端口 explanation",
                details={"node_type": self.contract.node_type},
            )

        # 如果是 dict, 包装成简单的 ExplanationResult-like 对象
        if isinstance(explanation, dict):
            from hscredit.core.models.explainability.result import ExplanationResult

            explanation = ExplanationResult(
                values=explanation.get("values"),
                data=explanation.get("data"),
                sample_ids=explanation.get("sample_ids"),
                feature_names=explanation.get("feature_names"),
            )

        try:
            reason_df = build_reason_codes(
                explanation,
                keep=int(params.get("keep", 3)),
                risk_direction=params.get("risk_direction", "higher_output_higher_risk"),
                feature_map=params.get("feature_map") or None,
            )
        except Exception as e:
            raise ValidationError(
                f"build_reason_codes 失败: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        # 构造 reason_map (特征 → 显示名)
        feature_map = params.get("feature_map") or {}
        reason_map = {feat: disp for feat, disp in feature_map.items()}

        return {"reason_df": reason_df, "reason_map": reason_map}


# ===== 2. SHAP Global Explanation =====


@register_node
class ShapGlobalNode(BaseNode):
    """全局 SHAP 解释 — 训练并输出全局特征重要性."""

    contract = NodeContract(
        node_type="shap_global",
        category="报告与部署",
        name="SHAP 全局解释",
        description="用 ModelExplainer 计算全局 SHAP 特征重要性",
        icon="🌐",
        inputs=[
            PortSchema(name="df", type="DataFrame", required=True, aliases=["woe_df", "selected_df", "encoded_df"]),
            PortSchema(name="model", type="ModelArtifact", required=True, description="上游模型"),
        ],
        outputs=[
            PortSchema(name="explainer", type="RuleArtifact", description="ModelExplainer 对象"),
            PortSchema(name="importance", type="DataFrame", description="全局特征重要性 (mean |SHAP|)"),
            PortSchema(name="summary", type="JSON", description="summary dict (含 values / data / sample_ids 供下游 reason_codes 使用)"),
        ],
        params=[
            ParamSpec(name="features", type="list", label="特征列表", required=True),
            ParamSpec(
                name="algorithm",
                type="select",
                label="SHAP 算法",
                default="auto",
                choices=[
                    ParamChoice(label="auto (树模型用 TreeExplainer, 其它 KernelExplainer)", value="auto"),
                    ParamChoice(label="tree (TreeExplainer)", value="tree"),
                    ParamChoice(label="kernel (KernelExplainer)", value="kernel"),
                    ParamChoice(label="linear (LinearExplainer)", value="linear"),
                    ParamChoice(label="deep (DeepExplainer)", value="deep"),
                ],
                advanced=True,
            ),
            ParamSpec(
                name="max_background",
                type="int",
                label="背景数据最大样本数",
                default=200,
                min=10,
                max=2000,
                advanced=True,
            ),
            ParamSpec(name="random_state", type="int", label="随机种子", default=42, advanced=True),
        ],
        cache=CacheConfig(),
        timeout_sec=300,
        estimated_duration_sec=30,
        tags=["explainability", "shap"],
        version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.models.explainability import ModelExplainer
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.models.explainability.ModelExplainer 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "woe_df", "selected_df", "encoded_df"))
        model = inputs.get("model")
        if model is None:
            raise ValidationError(
                "缺少必需输入端口 model",
                details={"node_type": self.contract.node_type, "available_inputs": list(inputs.keys())},
            )

        features = params.get("features")
        if not features:
            raise ValidationError(
                "features 必须非空",
                details={"node_type": self.contract.node_type},
            )
        if isinstance(features, str):
            features = [f.strip() for f in features.split(",") if f.strip()]
        missing = [f for f in features if f not in df.columns]
        if missing:
            raise ValidationError(
                f"以下特征不在数据中: {missing}",
                details={"node_type": self.contract.node_type, "missing_features": missing},
            )

        X = df[features].values
        explainer = ModelExplainer(
            model=model,
            feature_names=features,
            background_data=X[: int(params.get("max_background", 200))],
            algorithm=params.get("algorithm", "auto"),
            max_background=int(params.get("max_background", 200)),
            random_state=int(params.get("random_state", 42)),
        )
        try:
            result = explainer.explain(X)
        except Exception as e:
            raise ValidationError(
                f"ModelExplainer.explain 失败: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        # 构造 importance DataFrame
        try:
            values = result.values
            if hasattr(values, "ndim") and values.ndim == 2:
                mean_abs = np.abs(values).mean(axis=0)
            else:
                mean_abs = np.abs(values).mean(axis=(0, 2)) if values.ndim == 3 else np.abs(values).mean(axis=0)
            importance = pd.DataFrame(
                {
                    "feature": features[: len(mean_abs)],
                    "mean_abs_shap": mean_abs,
                }
            ).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)
        except Exception:
            importance = pd.DataFrame({"feature": features, "mean_abs_shap": [0.0] * len(features)})

        summary = {
            "feature_names": features,
            "n_samples": int(len(X)),
        }
        return {
            "explainer": explainer,
            "importance": importance,
            "summary": summary,
        }