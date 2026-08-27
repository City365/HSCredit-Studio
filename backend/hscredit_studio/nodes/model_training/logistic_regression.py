"""逻辑回归训练 — sklearn 兼容 + hscredit 扩展统计信息.

复用 ``hscredit.core.models.classical.LogisticRegression``。
训练后:

- 评估训练集 AUC / KS / Gini 等指标
- 输出 ``model`` 与 ``metrics`` 字典;``metrics`` 字段供下游报告节点使用
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
    ParamChoice,
    ParamSpec,
    PortSchema,
)


@register_node
class LogisticRegressionNode(BaseNode):
    """逻辑回归训练 — sklearn 兼容接口."""

    contract = NodeContract(
        node_type="logistic_regression",
        category="模型训练",
        name="逻辑回归训练",
        description="训练一个二分类逻辑回归模型（自动计算 VIF / P>|z| / 标准误差）",
        icon="📈",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["woe_df", "selected_df", "binned_df"])],
        outputs=[
            PortSchema(name="model", type="ModelArtifact", description="训练好的逻辑回归模型"),
            PortSchema(name="metrics", type="JSON", description="训练集评估指标字典"),
        ],
        params=[
            ParamSpec(name="target", type="str", label="目标列名", required=True),
            ParamSpec(name="features", type="list", label="特征列表", required=True),
            ParamSpec(
                name="C",
                type="float",
                label="正则化强度倒数",
                default=1.0,
                min=0.001,
                max=100.0,
                advanced=True,
            ),
            ParamSpec(
                name="penalty",
                type="str",
                label="正则化类型",
                default="l2",
                choices=[
                    ParamChoice(label="L1", value="l1"),
                    ParamChoice(label="L2", value="l2"),
                    ParamChoice(label="弹性网", value="elasticnet"),
                ],
            ),
            ParamSpec(
                name="max_iter",
                type="int",
                label="最大迭代次数",
                default=1000,
                min=10,
                max=10000,
                advanced=True,
            ),
            ParamSpec(name="random_state", type="int", label="随机种子", default=42),
            ParamSpec(
                name="eval_metric",
                type="multiselect",
                label="评估指标",
                default=["auc", "ks"],
                choices=[
                    ParamChoice(label="AUC", value="auc"),
                    ParamChoice(label="KS", value="ks"),
                    ParamChoice(label="Gini", value="gini"),
                ],
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=600,
        estimated_duration_sec=60,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        try:
            from hscredit.core.models.classical import LogisticRegression
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.models.classical.LogisticRegression 不可用: {e}",
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
        # features 为空时自动用 df 中除 target 外的所有数值列
        # （避免把字符串列如 device_os/source 喂给 LR 报 float 转换错误）
        if not features:
            numeric_cols = df.select_dtypes(include="number").columns.tolist()
            features = [c for c in numeric_cols if c != target]
        if not isinstance(features, list) or not features:
            raise ValidationError(
                "features 必须是非空列表",
                details={"node_type": self.contract.node_type, "features": features},
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

        penalty = params.get("penalty", "l2")
        kwargs: dict[str, Any] = {
            "C": float(params.get("C", 1.0)),
            "penalty": penalty,
            "max_iter": int(params.get("max_iter", 1000)),
            "random_state": int(params.get("random_state", 42)),
            "calculate_stats": True,
        }
        # 仅在 elasticnet 时需要 l1_ratio, 设为常用值
        if penalty == "elasticnet":
            kwargs["l1_ratio"] = 0.5

        try:
            model = LogisticRegression(**kwargs)
            model.fit(X, y)
        except Exception as e:
            raise ValidationError(
                f"逻辑回归训练失败: {e}",
                details={"node_type": self.contract.node_type, "penalty": penalty},
            ) from e

        eval_metrics = params.get("eval_metric") or ["auc", "ks"]
        try:
            metrics = model.evaluate(X, y, metrics=eval_metrics) or {}
        except Exception as e:
            metrics = {"warning": f"evaluate 失败: {type(e).__name__}: {e}"}
        return {"model": model, "metrics": metrics, "df": df}
