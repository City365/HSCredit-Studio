"""SHAP 模型解释节点 — 计算特征重要性 + 摘要.

输出:
- ``shap_values`` (JSON dict) — 特征名 → 平均 |SHAP| 值
- ``importance`` (DataFrame) — 排序好的特征重要性表 (特征 / 平均 SHAP / 标准差)
- ``summary_path`` (str) — 摘要图 PNG 本地路径 (供前端展示)
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np
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
    ParamSpec,
    PortSchema,
)


@register_node
class ShapExplanationNode(BaseNode):
    """SHAP 特征重要性分析 (TreeSHAP / KernelSHAP / LinearSHAP 自动选择)."""

    contract = NodeContract(
        node_type="shap_explanation",
        category="模型训练",
        name="SHAP 解释",
        description="用 SHAP 计算特征重要性, 输出排序后的重要性 + 摘要图 (PNG)",
        icon="🔬",
        inputs=[
            PortSchema(name="model", type="ModelArtifact", required=True, aliases=["lr_model", "score_card"]),
            PortSchema(name="df", type="DataFrame", required=True, aliases=["woe_df", "selected_df", "binned_df"]),
        ],
        outputs=[
            PortSchema(name="importance", type="DataFrame", description="特征重要性表"),
            PortSchema(name="shap_values", type="JSON", description="特征名 → 平均 |SHAP| 值"),
            PortSchema(name="summary_path", type="PNG", description="摘要图本地路径"),
        ],
        params=[
            ParamSpec(name="target", type="str", label="目标列名", required=True),
            ParamSpec(name="features", type="list", label="特征列表", required=True),
            ParamSpec(
                name="max_samples",
                type="int",
                label="最大解释样本数 (SHAP 计算开销)",
                default=200,
                min=50,
                max=2000,
                advanced=True,
            ),
            ParamSpec(
                name="output_dir",
                type="str",
                label="摘要图输出目录",
                default="./_shap",
                advanced=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=300,
        estimated_duration_sec=30,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        try:
            import shap
        except ImportError as e:
            raise DependencyError(
                "SHAP 库未安装, 请 pip install shap",
                details={"node_type": self.contract.node_type},
            ) from e

        import shap

        model = inputs["model"]
        df = inputs["df"]
        target = params["target"]
        features = params["features"]
        max_samples = int(params.get("max_samples", 200))
        output_dir = params.get("output_dir") or "./_shap"

        if not isinstance(features, list) or not features:
            raise ValidationError(
                "features 必须是非空列表",
                details={"node_type": self.contract.node_type},
            )
        missing = [c for c in features if c not in df.columns]
        if missing:
            raise FeatureNotFoundError(
                f"以下特征不在数据中: {missing}",
                details={"node_type": self.contract.node_type, "missing_features": missing},
            )
        if target not in df.columns:
            raise ValidationError(
                f"目标列 {target} 不存在",
                details={"node_type": self.contract.node_type, "target": target},
            )

        # 取样 (SHAP 计算开销随样本数线性增长)
        X = df[features].copy()
        X_sample = X.sample(n=max_samples, random_state=42) if len(X) > max_samples else X

        # 自动选择 explainer
        # sklearn 树模型 → TreeExplainer; 其它 → KernelExplainer
        try:
            if hasattr(model, "predict_proba") and hasattr(model, "estimators_"):
                # sklearn RF / GBDT
                explainer = shap.TreeExplainer(model)
            elif hasattr(model, "get_booster") or hasattr(model, "get_score"):
                # xgboost / lightgbm 原生接口
                explainer = shap.TreeExplainer(model)
            elif hasattr(model, "coef_"):
                # 线性模型
                explainer = shap.LinearExplainer(model, X_sample)
            else:
                # 通用 KernelExplainer (慢但通用)
                background = X_sample.iloc[: min(50, len(X_sample))]
                explainer = shap.KernelExplainer(model.predict_proba, background)
        except Exception:
            # 兜底
            background = X_sample.iloc[: min(50, len(X_sample))]
            explainer = shap.KernelExplainer(model.predict_proba, background)

        try:
            shap_values = explainer.shap_values(X_sample)
        except Exception as e:
            raise DependencyError(
                f"SHAP 计算失败: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        # 处理二分类返回 list 的情况
        sv = np.array(shap_values[-1]) if isinstance(shap_values, list) else np.array(shap_values)
        if sv.ndim == 3:
            sv = sv[:, :, -1]

        # 计算特征重要性
        mean_abs = np.abs(sv).mean(axis=0)
        std_abs = np.abs(sv).std(axis=0)
        importance = (
            pd.DataFrame(
                {
                    "feature": features,
                    "mean_abs_shap": mean_abs,
                    "std_abs_shap": std_abs,
                }
            )
            .sort_values("mean_abs_shap", ascending=False)
            .reset_index(drop=True)
        )

        # 输出 dict
        shap_dict = {f: float(v) for f, v in zip(features, mean_abs, strict=False)}

        # 生成摘要图 (PNG)
        os.makedirs(output_dir, exist_ok=True)
        summary_path = os.path.join(output_dir, "shap_summary.png")
        try:
            import matplotlib

            matplotlib.use("Agg")  # 无显示后端
            import matplotlib.pyplot as plt

            plt.figure(figsize=(8, max(4, len(features) * 0.4)))
            shap.summary_plot(sv, X_sample, feature_names=features, show=False)
            plt.tight_layout()
            plt.savefig(summary_path, dpi=100, bbox_inches="tight")
            plt.close()
        except Exception as e:
            # 摘要图生成失败, 但 SHAP 值已算好, 不阻塞
            summary_path = ""
            import logging

            logging.getLogger(__name__).warning(f"SHAP summary plot failed: {e}")

        return {
            "importance": importance,
            "shap_values": shap_dict,
            "summary_path": summary_path,
        }
