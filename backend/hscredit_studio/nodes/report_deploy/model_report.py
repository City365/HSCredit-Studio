"""ModelReport 生成 — Excel 多 sheet 模型评估报告.

复用 ``hscredit.report.ModelReport``;关键 API:

- ``ModelReport(model, datasets={'训练集': df, '测试集': df}, target='target')``
- ``report.to_excel(filepath)`` 生成多 sheet Excel 报告
- ``report.to_excel(...)`` 兼容评分卡对象, 自动调用 ``predict_score``

数据集拆分语义:

- ``train_df`` 必有, 名称统一为 ``训练集``。
- ``test_df`` 可选, 提供则命名为 ``测试集``。
- 训练/测试特征使用 ``features`` 列表; ``target`` 为目标列。
"""
from __future__ import annotations

import os
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
class ModelReportNode(BaseNode):
    """生成模型评估报告（Excel 格式，多 sheet 含 KS/LIFT/PSI 等）."""

    contract = NodeContract(
        node_type="model_report",
        category="报告与部署",
        name="ModelReport 生成",
        description="生成模型评估 Excel 报告（KS/AUC/PSI/分箱/特征重要性 等）",
        icon="📋",
        inputs=[
            PortSchema(name="model", type="ModelArtifact", required=False, aliases=["score_card"]),
            PortSchema(name="train_df", type="DataFrame", required=True, aliases=["df", "woe_df", "binned_df"]),
            PortSchema(name="test_df", type="DataFrame", required=False, aliases=["df", "woe_df"]),
        ],
        outputs=[
            PortSchema(name="report_path", type="Excel", description="Excel 报告路径"),
        ],
        params=[
            ParamSpec(name="target", type="str", label="训练目标列名", required=True),
            ParamSpec(name="features", type="list", label="训练特征列表", required=True),
            ParamSpec(
                name="target_test",
                type="str",
                label="测试目标列名（缺省同 target）",
                default="",
                advanced=True,
            ),
            ParamSpec(
                name="output_path",
                type="file",
                label="输出文件路径",
                default="/tmp/model_report.xlsx",
            ),
            ParamSpec(
                name="with_plots",
                type="bool",
                label="包含图表",
                default=True,
                advanced=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=900,
        estimated_duration_sec=120,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        try:
            from hscredit.report import ModelReport
        except ImportError as e:
            raise DependencyError(
                f"hscredit.report.ModelReport 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        # 兼容多种上游 key：model_report 上游可能是 score_card（key=score_card）或 logistic_regression（key=model）
        model = inputs.get("model")
        if model is None:
            model = inputs.get("score_card")
        # model 可选；若上游未提供仍能生成最简报告（仅含数据摘要）。
        train_df = inputs.get("train_df")
        if train_df is None:
            train_df = inputs.get("df")
        if train_df is None:
            train_df = inputs.get("woe_df")
        if train_df is None:
            train_df = inputs.get("binned_df")
        if train_df is None:
            raise ValidationError(
                "缺少 train_df / df / woe_df 输入",
                details={"node_type": self.contract.node_type, "available_inputs": list(inputs.keys())},
            )
        test_df = inputs.get("test_df")

        target = params["target"]
        features = params.get("features")
        # features 为空时自动用 train_df 中除 target 外的所有数值列
        if not features:
            numeric_cols = train_df.select_dtypes(include="number").columns.tolist()
            features = [c for c in numeric_cols if c != target]
        if not isinstance(features, list) or not features:
            raise ValidationError(
                "features 必须是非空列表",
                details={"node_type": self.contract.node_type},
            )

        # 校验列存在
        for col in features + [target]:
            if col not in train_df.columns:
                raise FeatureNotFoundError(
                    f"训练集缺少必需列: {col}",
                    details={"node_type": self.contract.node_type, "missing": col},
                )
        if test_df is not None:
            target_test = params.get("target_test") or target
            for col in features + [target_test]:
                if col not in test_df.columns:
                    raise FeatureNotFoundError(
                        f"测试集缺少必需列: {col}",
                        details={"node_type": self.contract.node_type, "missing": col},
                    )

        target_test = params.get("target_test") or target

        # 构造 datasets 字典
        # 把所有 datetime 列统一为 tz-naive（避免 hscredit 内部 timezone 混用）
        def _strip_tz(df: pd.DataFrame) -> pd.DataFrame:
            for col in df.select_dtypes(include="datetimetz").columns:
                df[col] = df[col].dt.tz_localize(None)
            return df
        train_df = _strip_tz(train_df.copy())
        if test_df is not None:
            test_df = _strip_tz(test_df.copy())
        datasets: dict[str, pd.DataFrame] = {"训练集": train_df[features + [target]].copy()}
        if test_df is not None:
            datasets["测试集"] = test_df[features + [target_test]].copy()

        try:
            # ModelReport 期望 model 是已训练分类器（sklearn 风格）。
            # hscredit 的 ModelReport 默认按 raw 特征评分，对已 woe 编码的特征不友好。
            # 因此传入一个 dummy 包装：只调用 model.predict_proba，并把 X_train 也传为 X_test
            # 避免内部要求 binner/encoder。
            import numpy as _np
            from hscredit.report.model_report import ModelReport as _MR

            class _IdentityModel:
                def __init__(self, inner):
                    self._inner = inner

                def predict_proba(self, X):
                    if hasattr(self._inner, "predict_proba"):
                        return self._inner.predict_proba(X)
                    if hasattr(self._inner, "predict"):
                        p = self._inner.predict(X)
                        return _np.column_stack([1 - p, p])
                    # 兜底：返回均匀概率
                    return _np.column_stack([_np.full(len(X), 0.5), _np.full(len(X), 0.5)])

                def predict(self, X):
                    if hasattr(self._inner, "predict"):
                        return self._inner.predict(X)
                    proba = self.predict_proba(X)
                    return (proba[:, 1] > 0.5).astype(int)

            wrapped_model = _IdentityModel(model) if model is not None else None

            # 用 X_train + y_train 显式传入，绕过 datasets 拆 target 时对 binner 的依赖
            X_train = train_df[features].copy()
            y_train = train_df[target].copy()
            report_kwargs: dict[str, Any] = {
                "feature_names": features,
                "X_train": X_train,
                "y_train": y_train,
            }
            if wrapped_model is not None:
                report_kwargs["model"] = wrapped_model
            report = _MR(**report_kwargs)
        except Exception as e:
            raise DependencyError(
                f"ModelReport 构造失败: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        output_path = params.get("output_path") or "/tmp/model_report.xlsx"
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        try:
            # 现代 ModelReport 提供 to_excel;保留 datasets 兼容构造路径
            report.datasets = datasets  # 兼容部分版本 ModelReport 直接读取 datasets
            report.to_excel(
                output_path,
                with_plots=bool(params.get("with_plots", True)),
            )
        except AttributeError:
            # 旧版 ModelReport 仅 datasets 构造 — 重新生成
            report = ModelReport(
                estimator=model,
                datasets=datasets,
                target=target,
                feature_names=features,
            )
            report.to_excel(
                output_path,
                with_plots=bool(params.get("with_plots", True)),
            )
        except Exception as e:
            raise ValidationError(
                f"生成 ModelReport 失败: {e}",
                details={"node_type": self.contract.node_type, "output_path": output_path},
            ) from e

        return {"report_path": output_path}
