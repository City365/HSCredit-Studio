"""XGBoost 训练节点 — 基于 hscredit.core.models.boosting.XGBoost.

提供企业级 XGBoost 训练能力:
- 自动 early stopping (eval_metric=auc)
- 特征重要性 (gain/cover/weight/total_gain/total_cover)
- 输出 model + metrics + importance

依赖: pip install hscredit[boost] (xgboost)
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
    ParamSpec,
    PortSchema,
)


@register_node
class XGBoostNode(BaseNode):
    """XGBoost 梯度提升树 (二分类) — 自带特征重要性."""

    contract = NodeContract(
        node_type="xgboost",
        category="模型训练",
        name="XGBoost 训练",
        description="XGBoost 二分类, 自动 early stopping + 特征重要性 (gain/cover/weight)",
        icon="🌲",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["woe_df", "selected_df", "binned_df"])],
        outputs=[
            PortSchema(name="model", type="ModelArtifact", description="训练好的 XGBoost 模型"),
            PortSchema(name="metrics", type="JSON", description="训练集评估指标 (AUC/KS/Gini)"),
            PortSchema(
                name="importance", type="DataFrame", description="特征重要性 (gain/cover/weight/total_gain/total_cover)"
            ),
        ],
        params=[
            ParamSpec(name="target", type="str", label="目标列名", required=True),
            ParamSpec(name="features", type="list", label="特征列表", required=True),
            ParamSpec(name="n_estimators", type="int", label="树数量 (boosting rounds)", default=300, min=10, max=5000),
            ParamSpec(name="max_depth", type="int", label="树最大深度", default=6, min=2, max=20),
            ParamSpec(name="learning_rate", type="float", label="学习率 (eta)", default=0.1, min=0.001, max=1.0),
            ParamSpec(
                name="subsample", type="float", label="样本采样比例", default=1.0, min=0.1, max=1.0, advanced=True
            ),
            ParamSpec(
                name="colsample_bytree",
                type="float",
                label="特征采样比例",
                default=1.0,
                min=0.1,
                max=1.0,
                advanced=True,
            ),
            ParamSpec(name="reg_lambda", type="float", label="L2 正则", default=1.0, min=0.0, advanced=True),
            ParamSpec(name="reg_alpha", type="float", label="L1 正则", default=0.0, min=0.0, advanced=True),
            ParamSpec(
                name="early_stopping_rounds", type="int", label="早停轮数", default=30, min=0, max=200, advanced=True
            ),
            ParamSpec(name="random_state", type="int", label="随机种子", default=42, advanced=True),
        ],
        cache=CacheConfig(),
        timeout_sec=900,
        estimated_duration_sec=60,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        try:
            from hscredit.core.models.boosting import XGBoost
        except ImportError as e:
            raise DependencyError(
                "XGBoost 未安装, 请 pip install hscredit[boost]",
                details={"node_type": self.contract.node_type, "package": "xgboost"},
            ) from e

        df = inputs["df"]
        target = params["target"]
        features = params["features"]

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

        X = df[features].values
        y = df[target].values

        # 划分 train/val (8:2) 用于 early stopping
        from sklearn.model_selection import train_test_split

        X_tr, X_va, y_tr, y_va = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

        model_kwargs = {
            "n_estimators": int(params.get("n_estimators", 300)),
            "max_depth": int(params.get("max_depth", 6)),
            "learning_rate": float(params.get("learning_rate", 0.1)),
            "subsample": float(params.get("subsample", 1.0)),
            "colsample_bytree": float(params.get("colsample_bytree", 1.0)),
            "reg_lambda": float(params.get("reg_lambda", 1.0)),
            "reg_alpha": float(params.get("reg_alpha", 0.0)),
            "random_state": int(params.get("random_state", 42)),
            "early_stopping_rounds": int(params.get("early_stopping_rounds", 30)),
        }

        model = XGBoost(**model_kwargs)
        try:
            model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        except Exception as e:
            raise DependencyError(
                f"XGBoost 训练失败: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        # 训练集评估
        metrics: dict[str, Any] = {}
        try:
            from sklearn.metrics import roc_auc_score

            y_pred_proba = model.predict_proba(X)[:, 1]
            metrics["auc"] = float(roc_auc_score(y, y_pred_proba))
            from hscredit.core.metrics import ks as ks_func

            metrics["ks"] = float(ks_func(y, y_pred_proba))
            metrics["gini"] = 2 * metrics["auc"] - 1
        except Exception as e:
            metrics["warning"] = f"指标计算失败: {e}"

        # 特征重要性
        importance = self._extract_importance(model, features)

        return {"model": model, "metrics": metrics, "importance": importance}

    def _extract_importance(self, model: Any, features: list[str]) -> pd.DataFrame:
        """提取 XGBoost 特征重要性 (gain/cover/weight/total_gain/total_cover)."""
        try:
            importance_dict = model.get_feature_importance() if hasattr(model, "get_feature_importance") else {}
        except Exception:
            importance_dict = {}

        if importance_dict:
            df = pd.DataFrame(importance_dict)
            df["feature"] = features[: len(df)]
            df = df.sort_values("gain", ascending=False).reset_index(drop=True)
        else:
            df = pd.DataFrame({"feature": features, "gain": [0.0] * len(features)})
        return df
