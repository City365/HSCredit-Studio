"""可视化节点族 — 10 个 PNG 输出节点 (Phase 6 B36 阶段 3.1).

封装 hscredit.core.viz 的核心绘图函数:

- ``plot_ks``        — KS 曲线 (ks_plot)
- ``plot_roc``       — ROC 曲线 (risk_plots.roc_plot)
- ``plot_lift``      — Lift 曲线 (risk_plots.lift_plot)
- ``plot_gain``      — Gain 曲线 (risk_plots.gain_plot)
- ``plot_calibration`` — 校准曲线 (risk_plots.calibration_plot)
- ``plot_binning``   — 分箱分布图 (viz.bin_plot)
- ``plot_corr``      — 相关性热力图 (viz.corr_plot)
- ``plot_feature_importance`` — 特征重要性 (risk_plots.feature_importance_plot)
- ``plot_vintage``   — Vintage 账龄曲线 (risk_plots.vintage_plot)
- ``plot_score_drift`` — 评分漂移图 (risk_plots 相关)

所有节点都输出 ``PNG`` 类型的产物 (经 executor 序列化到 S3).
"""

from __future__ import annotations

import io
import os
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


def _save_fig_to_png_bytes(fig) -> bytes:
    """matplotlib Figure → PNG bytes (供 executor 持久化)."""
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def _fig_or_axes(ax):
    """matplotlib axes → fig (兼容 ax 或 figure 输入)."""
    return ax.get_figure() if ax is not None and hasattr(ax, "get_figure") else ax


# ===== 1. KS 曲线 =====


@register_node
class PlotKSNode(BaseNode):
    contract = NodeContract(
        node_type="plot_ks",
        category="报告与部署",
        name="KS 曲线",
        description="KS 曲线图 (训练/测试 KS 对比)",
        icon="📈",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["scores", "score_df"])],
        outputs=[
            PortSchema(name="png", type="PNG", description="KS 曲线 PNG 字节流"),
        ],
        params=[
            ParamSpec(name="score_col", type="str", label="分数列名", required=True),
            ParamSpec(name="target_col", type="str", label="目标列名", required=True, workflow_scoped=True),
            ParamSpec(name="title", type="str", label="图表标题", default="KS Curve"),
            ParamSpec(name="figsize", type="str", label="图大小 (W,H)", default="16,8", advanced=True),
        ],
        cache=CacheConfig(),
        timeout_sec=120,
        estimated_duration_sec=5,
        tags=["viz"],
        version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.viz import ks_plot
        except ImportError as e:
            raise DependencyError(f"hscredit.core.viz.ks_plot 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "scores", "score_df"))
        score_col, target_col = params["score_col"], params["target_col"]
        for col in (score_col, target_col):
            if col not in df.columns:
                raise FeatureNotFoundError(f"列 {col} 不存在", details={"node_type": self.contract.node_type, "missing": col})
        try:
            fig_or_ax = ks_plot(
                df[score_col].values, df[target_col].values,
                title=params.get("title", "KS Curve"),
            )
        except Exception as e:
            raise ValidationError(f"KS plot 失败: {e}", details={"node_type": self.contract.node_type}) from e
        png_bytes = _save_fig_to_png_bytes(_fig_or_axes(fig_or_ax))
        return {"png": png_bytes}


# ===== 2. ROC 曲线 =====


@register_node
class PlotROCNode(BaseNode):
    contract = NodeContract(
        node_type="plot_roc",
        category="报告与部署",
        name="ROC 曲线",
        description="ROC 曲线 + AUC",
        icon="📉",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["scores", "score_df"])],
        outputs=[PortSchema(name="png", type="PNG")],
        params=[
            ParamSpec(name="score_col", type="str", label="分数列名", required=True),
            ParamSpec(name="target_col", type="str", label="目标列名", required=True, workflow_scoped=True),
        ],
        cache=CacheConfig(), timeout_sec=60, estimated_duration_sec=3,
        tags=["viz"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.viz.risk_plots import roc_plot
        except ImportError as e:
            raise DependencyError(f"hscredit.core.viz.risk_plots.roc_plot 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "scores", "score_df"))
        score_col, target_col = params["score_col"], params["target_col"]
        for col in (score_col, target_col):
            if col not in df.columns:
                raise FeatureNotFoundError(f"列 {col} 不存在", details={"node_type": self.contract.node_type})
        try:
            ax = roc_plot(df[target_col].values, df[score_col].values)
        except Exception as e:
            raise ValidationError(f"ROC plot 失败: {e}", details={"node_type": self.contract.node_type}) from e
        return {"png": _save_fig_to_png_bytes(_fig_or_axes(ax))}


# ===== 3. Lift 曲线 =====


@register_node
class PlotLiftNode(BaseNode):
    contract = NodeContract(
        node_type="plot_lift", category="报告与部署",
        name="Lift 曲线", description="Lift 提升曲线 (按分箱)",
        icon="🚀",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["scores", "score_df"])],
        outputs=[PortSchema(name="png", type="PNG")],
        params=[
            ParamSpec(name="score_col", type="str", label="分数列名", required=True),
            ParamSpec(name="target_col", type="str", label="目标列名", required=True, workflow_scoped=True),
            ParamSpec(name="n_bins", type="int", label="分箱数", default=10, min=2, max=50, advanced=True),
        ],
        cache=CacheConfig(), timeout_sec=60, estimated_duration_sec=3,
        tags=["viz"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.viz.risk_plots import lift_plot
        except ImportError as e:
            raise DependencyError(f"hscredit.core.viz.risk_plots.lift_plot 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "scores", "score_df"))
        score_col, target_col = params["score_col"], params["target_col"]
        for col in (score_col, target_col):
            if col not in df.columns:
                raise FeatureNotFoundError(f"列 {col} 不存在", details={"node_type": self.contract.node_type})
        try:
            ax = lift_plot(df[target_col].values, df[score_col].values, n_bins=int(params.get("n_bins", 10)))
        except Exception as e:
            raise ValidationError(f"Lift plot 失败: {e}", details={"node_type": self.contract.node_type}) from e
        return {"png": _save_fig_to_png_bytes(_fig_or_axes(ax))}


# ===== 4. Gain 曲线 =====


@register_node
class PlotGainNode(BaseNode):
    contract = NodeContract(
        node_type="plot_gain", category="报告与部署",
        name="Gain 曲线", description="Gain 增益曲线",
        icon="💎",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["scores", "score_df"])],
        outputs=[PortSchema(name="png", type="PNG")],
        params=[
            ParamSpec(name="score_col", type="str", label="分数列名", required=True),
            ParamSpec(name="target_col", type="str", label="目标列名", required=True, workflow_scoped=True),
            ParamSpec(name="n_bins", type="int", label="分箱数", default=10, min=2, max=50, advanced=True),
        ],
        cache=CacheConfig(), timeout_sec=60, estimated_duration_sec=3,
        tags=["viz"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.viz.risk_plots import gain_plot
        except ImportError as e:
            raise DependencyError(f"hscredit.core.viz.risk_plots.gain_plot 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "scores", "score_df"))
        score_col, target_col = params["score_col"], params["target_col"]
        for col in (score_col, target_col):
            if col not in df.columns:
                raise FeatureNotFoundError(f"列 {col} 不存在", details={"node_type": self.contract.node_type})
        try:
            ax = gain_plot(df[target_col].values, df[score_col].values, n_bins=int(params.get("n_bins", 10)))
        except Exception as e:
            raise ValidationError(f"Gain plot 失败: {e}", details={"node_type": self.contract.node_type}) from e
        return {"png": _save_fig_to_png_bytes(_fig_or_axes(ax))}


# ===== 5. 校准曲线 =====


@register_node
class PlotCalibrationNode(BaseNode):
    contract = NodeContract(
        node_type="plot_calibration", category="报告与部署",
        name="校准曲线", description="校准曲线 (predicted prob vs actual rate)",
        icon="🎚️",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["scores", "score_df"])],
        outputs=[PortSchema(name="png", type="PNG")],
        params=[
            ParamSpec(name="score_col", type="str", label="分数列名", required=True),
            ParamSpec(name="target_col", type="str", label="目标列名", required=True, workflow_scoped=True),
            ParamSpec(name="n_bins", type="int", label="分箱数", default=10, min=2, max=50, advanced=True),
        ],
        cache=CacheConfig(), timeout_sec=60, estimated_duration_sec=3,
        tags=["viz"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.viz.risk_plots import calibration_plot
        except ImportError as e:
            raise DependencyError(f"hscredit.core.viz.risk_plots.calibration_plot 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "scores", "score_df"))
        score_col, target_col = params["score_col"], params["target_col"]
        for col in (score_col, target_col):
            if col not in df.columns:
                raise FeatureNotFoundError(f"列 {col} 不存在", details={"node_type": self.contract.node_type})
        try:
            ax = calibration_plot(df[target_col].values, df[score_col].values, n_bins=int(params.get("n_bins", 10)))
        except Exception as e:
            raise ValidationError(f"Calibration plot 失败: {e}", details={"node_type": self.contract.node_type}) from e
        return {"png": _save_fig_to_png_bytes(_fig_or_axes(ax))}


# ===== 6. 分箱分布图 =====


@register_node
class PlotBinningNode(BaseNode):
    contract = NodeContract(
        node_type="plot_binning", category="报告与部署",
        name="分箱分布图", description="分箱分布图 (坏样本率 + 占比)",
        icon="📊",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["binned_df", "woe_df"])],
        outputs=[PortSchema(name="png", type="PNG")],
        params=[
            ParamSpec(name="feature_col", type="str", label="特征列名", required=True),
            ParamSpec(name="target_col", type="str", label="目标列名", required=True, workflow_scoped=True),
        ],
        cache=CacheConfig(), timeout_sec=60, estimated_duration_sec=3,
        tags=["viz"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.viz import bin_plot
        except ImportError as e:
            raise DependencyError(f"hscredit.core.viz.bin_plot 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "binned_df", "woe_df"))
        feature_col, target_col = params["feature_col"], params["target_col"]
        for col in (feature_col, target_col):
            if col not in df.columns:
                raise FeatureNotFoundError(f"列 {col} 不存在", details={"node_type": self.contract.node_type})
        try:
            fig_or_ax = bin_plot(df, target=target_col, feature=feature_col)
        except Exception as e:
            raise ValidationError(f"Bin plot 失败: {e}", details={"node_type": self.contract.node_type}) from e
        return {"png": _save_fig_to_png_bytes(_fig_or_axes(fig_or_ax))}


# ===== 7. 相关性热力图 =====


@register_node
class PlotCorrNode(BaseNode):
    contract = NodeContract(
        node_type="plot_corr", category="报告与部署",
        name="相关性热力图", description="特征相关性热力图 (Pearson)",
        icon="🔥",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["woe_df", "selected_df"])],
        outputs=[PortSchema(name="png", type="PNG")],
        params=[
            ParamSpec(name="features", type="list", label="特征列表 (留空=全部数值列)", default=[]),
            ParamSpec(name="method", type="select", label="相关系数",
                      default="pearson",
                      choices=[ParamChoice(label="pearson", value="pearson"),
                               ParamChoice(label="spearman", value="spearman"),
                               ParamChoice(label="kendall", value="kendall")],
                      advanced=True),
        ],
        cache=CacheConfig(), timeout_sec=60, estimated_duration_sec=3,
        tags=["viz"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.viz import corr_plot
        except ImportError as e:
            raise DependencyError(f"hscredit.core.viz.corr_plot 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "woe_df", "selected_df"))
        feats = params.get("features") or []
        if isinstance(feats, str):
            feats = [f.strip() for f in feats.split(",") if f.strip()]
        if not feats:
            feats = list(df.select_dtypes(include=[np.number]).columns)
        data = df[feats].corr(method=params.get("method", "pearson"))
        try:
            fig_or_ax = corr_plot(data)
        except Exception as e:
            raise ValidationError(f"Corr plot 失败: {e}", details={"node_type": self.contract.node_type}) from e
        return {"png": _save_fig_to_png_bytes(_fig_or_axes(fig_or_ax))}


# ===== 8. 特征重要性 =====


@register_node
class PlotFeatureImportanceNode(BaseNode):
    contract = NodeContract(
        node_type="plot_feature_importance", category="报告与部署",
        name="特征重要性图", description="特征重要性条形图 (top-N)",
        icon="📊",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["importance_df"])],
        outputs=[PortSchema(name="png", type="PNG")],
        params=[
            ParamSpec(name="feature_col", type="str", label="特征名列", default="feature"),
            ParamSpec(name="importance_col", type="str", label="重要性列", default="mean_abs_shap"),
            ParamSpec(name="top_n", type="int", label="Top N", default=20, min=1, max=200, advanced=True),
        ],
        cache=CacheConfig(), timeout_sec=60, estimated_duration_sec=3,
        tags=["viz"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.viz.risk_plots import feature_importance_plot
        except ImportError as e:
            raise DependencyError(f"hscredit.core.viz.risk_plots.feature_importance_plot 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "importance_df"))
        feature_col = params.get("feature_col", "feature")
        importance_col = params.get("importance_col", "mean_abs_shap")
        for col in (feature_col, importance_col):
            if col not in df.columns:
                raise FeatureNotFoundError(f"列 {col} 不存在", details={"node_type": self.contract.node_type})
        df_sorted = df.sort_values(importance_col, ascending=False).head(int(params.get("top_n", 20)))
        try:
            ax = feature_importance_plot(
                features=df_sorted[feature_col].tolist(),
                importance=df_sorted[importance_col].values,
                top_n=int(params.get("top_n", 20)),
            )
        except Exception as e:
            raise ValidationError(f"Feature importance plot 失败: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        return {"png": _save_fig_to_png_bytes(_fig_or_axes(ax))}


# ===== 9. Vintage 账龄曲线 =====


@register_node
class PlotVintageNode(BaseNode):
    contract = NodeContract(
        node_type="plot_vintage", category="报告与部署",
        name="Vintage 账龄曲线", description="Vintage 账龄分析曲线 (MOB vs bad rate)",
        icon="📅",
        inputs=[PortSchema(name="df", type="DataFrame", required=True)],
        outputs=[PortSchema(name="png", type="PNG")],
        params=[
            ParamSpec(name="mob_col", type="str", label="账龄列 (MOB)", required=True),
            ParamSpec(name="target_col", type="str", label="目标列", required=True, workflow_scoped=True),
            ParamSpec(name="cohort_col", type="str", label="队列列 (放款月)", required=True),
        ],
        cache=CacheConfig(), timeout_sec=60, estimated_duration_sec=5,
        tags=["viz"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.viz.risk_plots import vintage_plot
        except ImportError as e:
            raise DependencyError(f"hscredit.core.viz.risk_plots.vintage_plot 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df",))
        for col in (params["mob_col"], params["target_col"], params["cohort_col"]):
            if col not in df.columns:
                raise FeatureNotFoundError(f"列 {col} 不存在", details={"node_type": self.contract.node_type})
        try:
            ax = vintage_plot(df, mob_col=params["mob_col"], target_col=params["target_col"])
        except Exception as e:
            raise ValidationError(f"Vintage plot 失败: {e}", details={"node_type": self.contract.node_type}) from e
        return {"png": _save_fig_to_png_bytes(_fig_or_axes(ax))}


# ===== 10. 评分漂移图 (基于 psi_plot, 用 train/test score 对比) =====


@register_node
class PlotScoreDriftNode(BaseNode):
    contract = NodeContract(
        node_type="plot_score_drift", category="报告与部署",
        name="评分漂移图", description="PSI 漂移可视化 (train vs test)",
        icon="📊",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["scores", "score_df"])],
        outputs=[PortSchema(name="png", type="PNG")],
        params=[
            ParamSpec(name="score_col", type="str", label="分数列名", required=True),
            ParamSpec(name="time_col", type="str", label="时间分组列", required=False,
                      description="若提供, 按时间切分 train/test; 否则用前 50% / 后 50%"),
            ParamSpec(name="labels", type="str", label="分组标签 (逗号分隔, 2 个)",
                      default="train,test", advanced=True),
        ],
        cache=CacheConfig(), timeout_sec=60, estimated_duration_sec=3,
        tags=["viz"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.viz import psi_plot
        except ImportError as e:
            raise DependencyError(f"hscredit.core.viz.psi_plot 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "scores", "score_df"))
        score_col = params["score_col"]
        if score_col not in df.columns:
            raise FeatureNotFoundError(f"列 {score_col} 不存在", details={"node_type": self.contract.node_type})
        scores = df[score_col].astype(float).values
        time_col = params.get("time_col")
        if time_col:
            if time_col not in df.columns:
                raise FeatureNotFoundError(f"时间列 {time_col} 不存在",
                                           details={"node_type": self.contract.node_type, "time_col": time_col})
            groups = df.groupby(time_col)
            keys = sorted(groups.groups.keys())
            if len(keys) < 2:
                raise ValidationError(f"时间列 {time_col} 至少需要 2 个分组",
                                      details={"node_type": self.contract.node_type})
            expected = groups.get_group(keys[0])[score_col].astype(float).values
            actual = pd.concat([groups.get_group(k)[score_col] for k in keys[1:]]).astype(float).values
            labels = [str(keys[0]), "+".join(str(k) for k in keys[1:])]
        else:
            n = len(scores)
            expected, actual = scores[: n // 2], scores[n // 2:]
            labels = params.get("labels", "train,test").split(",")[:2]
        try:
            fig_or_ax = psi_plot(expected, actual, labels=labels)
        except Exception as e:
            raise ValidationError(f"Score drift plot 失败: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        return {"png": _save_fig_to_png_bytes(_fig_or_axes(fig_or_ax))}