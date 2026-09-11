"""高级节点 — 8 个阶段 4 节点 (Phase 6 B36 阶段 4).

覆盖 hscredit 高级能力:

校准 (3):
- ``platt_calibration`` — Platt Scaling (logistic on log-odds)
- ``isotonic_calibration`` — Isotonic Regression (non-parametric)
- ``beta_calibration`` — Beta Calibration

调参 (1):
- ``optuna_tuner`` — Optuna AutoTuner (xgboost/lightgbm/catboost/...)

评分漂移 (1):
- ``score_drift`` — ScoreDriftCalibrator (linear/quantile/binning)

反事实 (1):
- ``counterfactual`` — CounterfactualExplainer

报告 (2):
- ``model_explain_report`` — model_explain_report (全局解释报告)
- ``feature_analyzer`` — feature_analyzer (特征分析)
"""

from __future__ import annotations

from typing import Any

import numpy as np
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


def _calibration_run_node(node_type: str, class_path: str, class_name: str, extra: list[str]):
    """通用校准节点 run() 工厂."""
    def run(self, inputs, params):
        try:
            import importlib
            mod = importlib.import_module(class_path)
            cls = getattr(mod, class_name)
        except (ImportError, AttributeError) as e:
            raise DependencyError(
                f"{class_path}.{class_name} 不可用: {e}",
                details={"node_type": node_type, "class": class_name},
            ) from e

        df = resolve_dataframe_input(inputs, node_type, aliases=("df", "scores", "score_df"))
        score_col = params["score_col"]
        target_col = params.get("target_col")
        if score_col not in df.columns:
            raise FeatureNotFoundError(f"分数列 {score_col} 不存在", details={"node_type": node_type})
        if target_col and target_col not in df.columns:
            raise FeatureNotFoundError(f"目标列 {target_col} 不存在", details={"node_type": node_type})
        if not target_col:
            raise ValidationError("target_col 必填 (校准需要真实标签)",
                                  details={"node_type": node_type})

        y_prob = df[score_col].astype(float).values
        y_true = df[target_col].astype(int).values

        kwargs: dict[str, Any] = {
            "n_bins": int(params.get("n_bins", 10)),
            "strategy": params.get("strategy", "uniform"),
        }
        for k in extra:
            if k in params:
                kwargs[k] = params[k]

        try:
            calibrator = cls(**kwargs)
            calibrator.fit(y_prob, y_true)
            y_calibrated = calibrator.transform(y_prob) if hasattr(calibrator, "transform") else calibrator.predict(y_prob)
        except Exception as e:
            raise ValidationError(f"{class_name} 校准失败: {e}",
                                  details={"node_type": node_type}) from e

        out_df = df.copy()
        out_df[f"{score_col}_calibrated"] = y_calibrated
        return {"calibrator": calibrator, "calibrated_df": out_df}

    return run


def _make_calibration_node(node_type, class_name, display_name, description, icon, extra_params=None):
    extra_params = extra_params or []
    extra_keys = [p.name for p in extra_params]

    node_contract = NodeContract(
        node_type=node_type,
        category="模型训练",
        name=display_name,
        description=description,
        icon=icon,
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["scores", "score_df"])],
        outputs=[
            PortSchema(name="calibrator", type="ModelArtifact", description="训练好的校准器"),
            PortSchema(name="calibrated_df", type="DataFrame", description="校准后的 DataFrame (含 *_calibrated 列)"),
        ],
        params=[
            ParamSpec(name="score_col", type="str", label="原始分数/概率列", required=True),
            ParamSpec(name="target_col", type="str", label="实际标签列", required=True, workflow_scoped=True),
            ParamSpec(name="n_bins", type="int", label="分箱数", default=10, min=2, max=50, advanced=True),
            ParamSpec(name="strategy", type="select", label="分箱策略",
                      default="uniform",
                      choices=[ParamChoice(label="uniform", value="uniform"),
                               ParamChoice(label="quantile", value="quantile")],
                      advanced=True),
            *extra_params,
        ],
        cache=CacheConfig(), timeout_sec=120, estimated_duration_sec=5,
        tags=["calibration"], version="1.0.0",
    )

    @register_node
    class _GenNode(BaseNode):
        contract = node_contract
    setattr(_GenNode, "run", _calibration_run_node(
        node_type, "hscredit.core.models.calibration.methods", class_name, extra_keys,
    ))
    _GenNode.__name__ = f"{class_name}Node"
    return _GenNode


# ===== 3 个校准节点 =====

PlattCalibrationNode = _make_calibration_node(
    node_type="platt_calibration",
    class_name="PlattCalibrator",
    display_name="Platt 校准",
    description="Platt Scaling — 在 log-odds 上拟合逻辑回归, 适合 Sigmoid 模型",
    icon="🎯",
    extra_params=[
        ParamSpec(name="C", type="float", label="Logistic C (正则倒数)",
                  default=1.0, min=0.001, max=1000.0, advanced=True),
    ],
)

IsotonicCalibrationNode = _make_calibration_node(
    node_type="isotonic_calibration",
    class_name="IsotonicCalibrator",
    display_name="Isotonic 校准",
    description="Isotonic Regression — 保序回归, 非参数, 适合样本充足",
    icon="📏",
    extra_params=[
        ParamSpec(name="out_of_bounds", type="select", label="越界处理",
                  default="clip",
                  choices=[ParamChoice(label="clip", value="clip"),
                           ParamChoice(label="nan", value="nan"),
                           ParamChoice(label="raise", value="raise")],
                  advanced=True),
    ],
)

BetaCalibrationNode = _make_calibration_node(
    node_type="beta_calibration",
    class_name="BetaCalibrator",
    display_name="Beta 校准",
    description="Beta Calibration — 适合非对称分布的分数",
    icon="β",
)


# ===== Optuna AutoTuner =====


@register_node
class OptunaTunerNode(BaseNode):
    contract = NodeContract(
        node_type="optuna_tuner",
        category="模型训练",
        name="Optuna 自动调参",
        description="AutoTuner — 基于 Optuna 的自动超参搜索 (xgboost/lightgbm/catboost/...)",
        icon="🔍",
        inputs=[
            PortSchema(name="df", type="DataFrame", required=True, aliases=["woe_df", "selected_df", "encoded_df"]),
        ],
        outputs=[
            PortSchema(name="tuner", type="ModelArtifact", description="AutoTuner 实例"),
            PortSchema(name="best_params", type="JSON", description="最优超参 (dict)"),
            PortSchema(name="best_model", type="ModelArtifact", description="最优模型 (可选)"),
        ],
        params=[
            ParamSpec(name="target_col", type="str", label="目标列", required=True, workflow_scoped=True),
            ParamSpec(name="features", type="list", label="特征列表", required=True),
            ParamSpec(name="model_type", type="select", label="模型类型",
                      default="xgboost",
                      choices=[ParamChoice(label="xgboost", value="xgboost"),
                               ParamChoice(label="lightgbm", value="lightgbm"),
                               ParamChoice(label="catboost", value="catboost"),
                               ParamChoice(label="randomforest", value="randomforest"),
                               ParamChoice(label="gradientboosting", value="gradientboosting"),
                               ParamChoice(label="logisticregression", value="logisticregression")]),
            ParamSpec(name="metric", type="select", label="优化指标",
                      default="ks",
                      choices=[ParamChoice(label="ks", value="ks"),
                               ParamChoice(label="auc", value="auc"),
                               ParamChoice(label="gini", value="gini"),
                               ParamChoice(label="accuracy", value="accuracy"),
                               ParamChoice(label="f1", value="f1")]),
            ParamSpec(name="n_trials", type="int", label="试验次数", default=50, min=1, max=1000, advanced=True),
            ParamSpec(name="cv", type="int", label="交叉验证折数", default=5, min=2, max=20, advanced=True),
            ParamSpec(name="random_state", type="int", label="随机种子", default=42, advanced=True),
        ],
        cache=CacheConfig(), timeout_sec=3600, estimated_duration_sec=300,
        tags=["tuning", "optuna"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.models import AutoTuner
        except ImportError as e:
            raise DependencyError(f"hscredit.core.models.AutoTuner 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e

        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "woe_df", "selected_df", "encoded_df"))
        target_col = params["target_col"]
        if target_col not in df.columns:
            raise FeatureNotFoundError(f"目标列 {target_col} 不存在",
                                       details={"node_type": self.contract.node_type, "target_col": target_col})
        features = params.get("features") or []
        if isinstance(features, str):
            features = [f.strip() for f in features.split(",") if f.strip()]
        if not features:
            raise ValidationError("features 不能为空", details={"node_type": self.contract.node_type})
        missing = [f for f in features if f not in df.columns]
        if missing:
            raise FeatureNotFoundError(f"以下特征不存在: {missing}",
                                       details={"node_type": self.contract.node_type, "missing": missing})

        try:
            tuner = AutoTuner.create(
                model_type=params["model_type"],
                metric=params.get("metric", "ks"),
                target=target_col,
                cv=int(params.get("cv", 5)),
                random_state=int(params.get("random_state", 42)),
            )
            best_params = tuner.fit(
                df[features], df[target_col], n_trials=int(params.get("n_trials", 50)),
            )
        except Exception as e:
            raise ValidationError(f"AutoTuner.fit 失败: {e}",
                                  details={"node_type": self.contract.node_type}) from e

        try:
            best_model = tuner.get_best_model() if hasattr(tuner, "get_best_model") else None
        except Exception:
            best_model = None

        return {"tuner": tuner, "best_params": best_params, "best_model": best_model}


# ===== 评分漂移校准 =====


@register_node
class ScoreDriftNode(BaseNode):
    contract = NodeContract(
        node_type="score_drift",
        category="模型训练",
        name="评分漂移校准",
        description="ScoreDriftCalibrator — 修复生产分数相对训练分数的分布偏移 (linear/quantile/binning)",
        icon="🎯",
        inputs=[
            PortSchema(name="df", type="DataFrame", required=True, aliases=["scores", "score_df"]),
            PortSchema(name="model", type="ModelArtifact", required=True, description="上游模型"),
        ],
        outputs=[
            PortSchema(name="calibrator", type="ModelArtifact", description="训练好的漂移校准器"),
            PortSchema(name="calibrated_df", type="DataFrame", description="校准后的 DataFrame"),
        ],
        params=[
            ParamSpec(name="target_col", type="str", label="目标列", required=True, workflow_scoped=True),
            ParamSpec(name="method", type="select", label="校准方法",
                      default="linear",
                      choices=[ParamChoice(label="linear (线性)", value="linear"),
                               ParamChoice(label="quantile (分位数对齐)", value="quantile"),
                               ParamChoice(label="binning (分箱重映射)", value="binning")]),
            ParamSpec(name="reference_scores", type="list", label="参考分数 (留空用全量数据训练期分数)",
                      default=[], advanced=True),
            ParamSpec(name="clip_bounds", type="bool", label="截断到 [0,1]",
                      default=True, advanced=True),
        ],
        cache=CacheConfig(), timeout_sec=300, estimated_duration_sec=30,
        tags=["calibration", "drift"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.models.scorecard import ScoreDriftCalibrator
        except ImportError as e:
            raise DependencyError(f"ScoreDriftCalibrator 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e

        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "scores", "score_df"))
        model = inputs.get("model")
        if model is None:
            raise ValidationError("缺少必需输入端口 model",
                                  details={"node_type": self.contract.node_type})
        target_col = params.get("target_col")
        if target_col not in df.columns:
            raise FeatureNotFoundError(f"目标列 {target_col} 不存在",
                                       details={"node_type": self.contract.node_type})

        ref_scores = params.get("reference_scores") or None
        if ref_scores and not isinstance(ref_scores, np.ndarray):
            ref_scores = np.asarray(ref_scores, dtype=float)

        try:
            calibrator = ScoreDriftCalibrator(
                method=params.get("method", "linear"),
                reference_scores=ref_scores,
                clip_bounds=bool(params.get("clip_bounds", True)),
                target=target_col,
            )
            # X: 数值特征列 (除 target)
            feature_cols = [c for c in df.columns if c != target_col]
            calibrator.fit(model, df[feature_cols], df[target_col].values)
            scores = calibrator.transform(df[feature_cols]) if hasattr(calibrator, "transform") else calibrator.predict(df[feature_cols])
        except Exception as e:
            raise ValidationError(f"ScoreDriftCalibrator.fit 失败: {e}",
                                  details={"node_type": self.contract.node_type}) from e

        out_df = df.copy()
        out_df["score_drift_calibrated"] = scores
        return {"calibrator": calibrator, "calibrated_df": out_df}


# ===== Counterfactual Explainer =====


@register_node
class CounterfactualNode(BaseNode):
    contract = NodeContract(
        node_type="counterfactual",
        category="报告与部署",
        name="反事实分析",
        description="CounterfactualExplainer — 搜索最小特征变更方案 (模型条件下的非因果建议)",
        icon="🔄",
        inputs=[
            PortSchema(name="df", type="DataFrame", required=True, aliases=["woe_df", "selected_df"]),
            PortSchema(name="model", type="ModelArtifact", required=True, description="上游模型"),
        ],
        outputs=[
            PortSchema(name="explainer", type="ModelArtifact", description="CounterfactualExplainer"),
            PortSchema(name="counterfactuals", type="DataFrame", description="反事实结果 (含 cf_* 列)"),
        ],
        params=[
            ParamSpec(name="features", type="list", label="特征列表", required=True),
            ParamSpec(name="target_col", type="str", label="目标列", required=True, workflow_scoped=True),
            ParamSpec(name="max_candidates", type="int", label="每特征最大候选数",
                      default=100, min=10, max=1000, advanced=True),
            ParamSpec(name="positive_class", type="int", label="正类标签", default=1, advanced=True),
        ],
        cache=CacheConfig(), timeout_sec=300, estimated_duration_sec=60,
        tags=["explainability", "counterfactual"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.models.explainability import CounterfactualExplainer
        except ImportError as e:
            raise DependencyError(f"CounterfactualExplainer 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e

        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "woe_df", "selected_df"))
        model = inputs.get("model")
        if model is None:
            raise ValidationError("缺少必需输入端口 model",
                                  details={"node_type": self.contract.node_type})
        features = params.get("features") or []
        if isinstance(features, str):
            features = [f.strip() for f in features.split(",") if f.strip()]
        if not features:
            raise ValidationError("features 不能为空",
                                  details={"node_type": self.contract.node_type})
        missing = [f for f in features if f not in df.columns]
        if missing:
            raise FeatureNotFoundError(f"以下特征不存在: {missing}",
                                       details={"node_type": self.contract.node_type, "missing": missing})

        try:
            explainer = CounterfactualExplainer(
                model=model,
                reference_data=df[features],
                max_candidates=int(params.get("max_candidates", 100)),
                positive_class=int(params.get("positive_class", 1)),
            )
            cf = explainer.explain(df[features].head(50))  # 限制样本数避免爆炸
        except Exception as e:
            raise ValidationError(f"CounterfactualExplainer 失败: {e}",
                                  details={"node_type": self.contract.node_type}) from e

        return {"explainer": explainer, "counterfactuals": cf}


# ===== model_explain_report =====


@register_node
class ModelExplainReportNode(BaseNode):
    contract = NodeContract(
        node_type="model_explain_report",
        category="报告与部署",
        name="模型全局解释报告",
        description="model_explain_report — 全局 SHAP 解释报告 (含图表)",
        icon="📑",
        inputs=[
            PortSchema(name="df", type="DataFrame", required=True, aliases=["woe_df", "selected_df"]),
            PortSchema(name="model", type="ModelArtifact", required=True),
        ],
        outputs=[
            PortSchema(name="report", type="Any", description="报告对象 (含 .save_*)"),
            PortSchema(name="importance", type="DataFrame", description="全局特征重要性"),
        ],
        params=[
            ParamSpec(name="features", type="list", label="特征列表", required=True),
            ParamSpec(name="target_col", type="str", label="目标列", required=True, workflow_scoped=True),
            ParamSpec(name="max_background", type="int", label="背景样本数",
                      default=200, min=10, max=2000, advanced=True),
        ],
        cache=CacheConfig(), timeout_sec=600, estimated_duration_sec=60,
        tags=["explainability", "report"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.models.explainability import model_explain_report
        except ImportError as e:
            raise DependencyError(f"model_explain_report 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e

        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "woe_df", "selected_df"))
        model = inputs.get("model")
        if model is None:
            raise ValidationError("缺少必需输入端口 model",
                                  details={"node_type": self.contract.node_type})
        features = params.get("features") or []
        if isinstance(features, str):
            features = [f.strip() for f in features.split(",") if f.strip()]
        missing = [f for f in features if f not in df.columns]
        if missing:
            raise FeatureNotFoundError(f"特征缺失: {missing}",
                                       details={"node_type": self.contract.node_type})

        try:
            report = model_explain_report(
                model=model,
                X=df[features],
                feature_names=features,
                max_background=int(params.get("max_background", 200)),
            )
        except Exception as e:
            raise ValidationError(f"model_explain_report 失败: {e}",
                                  details={"node_type": self.contract.node_type}) from e

        try:
            importance = report.importance if hasattr(report, "importance") else pd.DataFrame(
                {"feature": features, "importance": [0.0] * len(features)}
            )
        except Exception:
            importance = pd.DataFrame({"feature": features, "importance": [0.0] * len(features)})

        return {"report": report, "importance": importance}


# ===== feature_analyzer =====


@register_node
class FeatureAnalyzerNode(BaseNode):
    contract = NodeContract(
        node_type="feature_analyzer",
        category="EDA",
        name="特征深度分析",
        description="feature_analyzer — 特征类型推断/缺失/分布/异常值/稀有类别 一体化分析",
        icon="🔬",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["selected_df", "woe_df"])],
        outputs=[
            PortSchema(name="type_inference", type="DataFrame", description="类型推断"),
            PortSchema(name="missing", type="DataFrame", description="缺失率"),
            PortSchema(name="outliers", type="DataFrame", description="异常值"),
            PortSchema(name="rare_categories", type="DataFrame", description="稀有类别"),
        ],
        params=[
            ParamSpec(name="features", type="list", label="特征列表 (留空=全部)", default=[]),
            ParamSpec(name="outlier_method", type="select", label="异常值方法",
                      default="iqr",
                      choices=[ParamChoice(label="iqr (四分位)", value="iqr"),
                               ParamChoice(label="zscore (3-sigma)", value="zscore")],
                      advanced=True),
            ParamSpec(name="rare_threshold", type="float", label="稀有类别阈值 (占比<)",
                      default=0.01, min=0.0, max=0.5, advanced=True),
        ],
        cache=CacheConfig(), timeout_sec=300, estimated_duration_sec=30,
        tags=["eda", "feature_analysis"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.eda import (
                feature_type_inference, missing_analysis,
                outlier_detection, rare_category_detection,
            )
        except ImportError as e:
            raise DependencyError(f"hscredit.core.eda 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e

        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "selected_df", "woe_df"))
        features = params.get("features") or []
        if isinstance(features, str):
            features = [f.strip() for f in features.split(",") if f.strip()]
        if not features:
            features = list(df.columns)

        try:
            type_df = feature_type_inference(df[features])
        except Exception:
            type_df = pd.DataFrame()
        try:
            missing_df = missing_analysis(df[features])
        except Exception:
            missing_df = pd.DataFrame()
        try:
            outlier_df = outlier_detection(df[features], method=params.get("outlier_method", "iqr"))
        except Exception:
            outlier_df = pd.DataFrame()
        try:
            rare_df = rare_category_detection(df[features], threshold=float(params.get("rare_threshold", 0.01)))
        except Exception:
            rare_df = pd.DataFrame()

        return {
            "type_inference": type_df,
            "missing": missing_df,
            "outliers": outlier_df,
            "rare_categories": rare_df,
        }