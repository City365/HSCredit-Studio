"""模型评估节点族 — 3 个评估指标节点 (Phase 6 B36 阶段 2.1).

封装 hscredit.core.metrics 的核心指标:

- ``ks_auc_metrics`` — KS / AUC / Gini / Lift 等分类指标
- ``psi_metrics`` — PSI 跨期稳定性 (含详细分箱表)
- ``csi_metrics`` — CSI 跨段稳定性 (按特征分箱后的 PSI)
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


def _validate_pair(df: pd.DataFrame, actual_col: str, score_col: str, node_type: str) -> tuple[np.ndarray, np.ndarray]:
    if actual_col not in df.columns:
        raise FeatureNotFoundError(
            f"实际标签列 {actual_col} 不存在",
            details={"node_type": node_type, "actual_col": actual_col},
        )
    if score_col not in df.columns:
        raise FeatureNotFoundError(
            f"分数/概率列 {score_col} 不存在",
            details={"node_type": node_type, "score_col": score_col},
        )
    y_true = df[actual_col].astype(int).values
    y_score = df[score_col].astype(float).values
    if len(set(y_true)) < 2:
        raise ValidationError(
            f"实际标签列 {actual_col} 至少需要 2 个类别",
            details={"node_type": node_type},
        )
    if np.any(np.isnan(y_score)):
        raise ValidationError(
            f"分数列 {score_col} 含有 NaN",
            details={"node_type": node_type},
        )
    return y_true, y_score


# ===== 1. KS / AUC / Gini / Lift =====


@register_node
class KSAUCMetricsNode(BaseNode):
    """KS / AUC / Gini / Lift 综合评估."""

    contract = NodeContract(
        node_type="ks_auc_metrics",
        category="报告与部署",
        name="KS/AUC/Lift 评估",
        description="基于预测分数计算 KS / AUC / Gini / Lift 等分类指标",
        icon="📏",
        inputs=[
            PortSchema(name="df", type="DataFrame", required=True, aliases=["scores", "score_df", "selected_df", "woe_df"]),
        ],
        outputs=[
            PortSchema(name="metrics", type="JSON", description="指标 dict (ks/auc/gini/lift/...)"),
            PortSchema(name="ks_table", type="DataFrame", description="KS 分箱表"),
            PortSchema(name="lift_table", type="DataFrame", description="Lift 分箱表"),
        ],
        params=[
            ParamSpec(name="actual_col", type="str", label="实际标签列名", required=True),
            ParamSpec(name="score_col", type="str", label="分数/概率列名", required=True),
            ParamSpec(
                name="n_bins",
                type="int",
                label="分箱数",
                default=10,
                min=2,
                max=50,
                advanced=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=120,
        estimated_duration_sec=5,
        tags=["metrics", "classification"],
        version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.metrics import ks, auc, gini, lift_table, ks_bucket
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.metrics 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "scores", "score_df", "selected_df", "woe_df"))
        actual_col = params["actual_col"]
        score_col = params["score_col"]
        n_bins = int(params.get("n_bins", 10))

        y_true, y_score = _validate_pair(df, actual_col, score_col, self.contract.node_type)

        metrics: dict[str, Any] = {
            "ks": float(ks(y_true, y_score)),
            "auc": float(auc(y_true, y_score)),
            "gini": float(gini(y_true, y_score)),
        }

        try:
            ks_df = ks_bucket(y_true, y_score, n_bins=n_bins)
        except Exception:
            ks_df = pd.DataFrame()
        try:
            lift_df = lift_table(y_true, y_score, n_bins=n_bins)
        except Exception:
            lift_df = pd.DataFrame()

        return {"metrics": metrics, "ks_table": ks_df, "lift_table": lift_df}


# ===== 2. PSI 跨期稳定性 =====


@register_node
class PSIMetricsNode(BaseNode):
    """PSI (Population Stability Index) 跨期稳定性评估."""

    contract = NodeContract(
        node_type="psi_metrics",
        category="报告与部署",
        name="PSI 稳定性",
        description="计算 PSI 跨期稳定性 (含分箱级详细贡献)",
        icon="📆",
        inputs=[
            PortSchema(name="df", type="DataFrame", required=True, aliases=["scores", "score_df"]),
        ],
        outputs=[
            PortSchema(name="psi_value", type="JSON", description="PSI 总值 (float)"),
            PortSchema(name="psi_table", type="DataFrame", description="PSI 分箱贡献表"),
            PortSchema(name="psi_rating", type="Any", description="稳定性评级 (stable/warning/unstable)"),
        ],
        params=[
            ParamSpec(name="score_col", type="str", label="分数列名", required=True),
            ParamSpec(
                name="method",
                type="select",
                label="分箱方法",
                default="quantile",
                choices=[
                    ParamChoice(label="quantile (等频)", value="quantile"),
                    ParamChoice(label="uniform (等宽)", value="uniform"),
                    ParamChoice(label="tree (决策树)", value="tree"),
                ],
                advanced=True,
            ),
            ParamSpec(name="max_n_bins", type="int", label="最大分箱数", default=10, min=2, max=50, advanced=True),
            ParamSpec(
                name="time_col",
                type="str",
                label="时间分组列 (可选用 train/test 切分)",
                default=None,
                advanced=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=120,
        estimated_duration_sec=5,
        tags=["metrics", "stability"],
        version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.metrics import psi, psi_table, psi_rating
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.metrics.psi 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "scores", "score_df"))
        score_col = params["score_col"]
        if score_col not in df.columns:
            raise FeatureNotFoundError(
                f"分数列 {score_col} 不存在",
                details={"node_type": self.contract.node_type, "score_col": score_col},
            )

        scores = df[score_col].astype(float).values
        time_col = params.get("time_col")
        if time_col:
            if time_col not in df.columns:
                raise FeatureNotFoundError(
                    f"时间列 {time_col} 不存在",
                    details={"node_type": self.contract.node_type, "time_col": time_col},
                )
            # 按时间列分组: 第一组作为 expected, 其余合并为 actual
            groups = df.groupby(time_col)
            sorted_keys = sorted(groups.groups.keys())
            if len(sorted_keys) < 2:
                raise ValidationError(
                    f"时间列 {time_col} 至少需要 2 个分组",
                    details={"node_type": self.contract.node_type},
                )
            expected = groups.get_group(sorted_keys[0])[score_col].astype(float).values
            actual = pd.concat(
                [groups.get_group(k)[score_col] for k in sorted_keys[1:]]
            ).astype(float).values
        else:
            # 默认前 50% 为 expected, 后 50% 为 actual
            n = len(scores)
            expected = scores[: n // 2]
            actual = scores[n // 2:]

        try:
            psi_value = float(
                psi(expected, actual, method=params.get("method", "quantile"),
                    max_n_bins=int(params.get("max_n_bins", 10)))
            )
            psi_df = psi_table(
                expected, actual, method=params.get("method", "quantile"),
                max_n_bins=int(params.get("max_n_bins", 10)),
            )
            rating = psi_rating(psi_value)
        except Exception as e:
            raise ValidationError(
                f"PSI 计算失败: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        return {"psi_value": psi_value, "psi_table": psi_df, "psi_rating": rating}


# ===== 3. CSI 跨段稳定性 =====


@register_node
class CSIMetricsNode(BaseNode):
    """CSI (Characteristic Stability Index) 按特征分箱的稳定性."""

    contract = NodeContract(
        node_type="csi_metrics",
        category="报告与部署",
        name="CSI 稳定性",
        description="按特征分箱的稳定性指标 (CSI), 类似 PSI 但跨段对比",
        icon="🎚️",
        inputs=[
            PortSchema(name="df", type="DataFrame", required=True, aliases=["scores", "score_df"]),
        ],
        outputs=[
            PortSchema(name="csi_value", type="JSON", description="CSI 总值 (float)"),
            PortSchema(name="csi_table", type="DataFrame", description="CSI 分段表"),
        ],
        params=[
            ParamSpec(name="score_col", type="str", label="分数列名", required=True),
            ParamSpec(name="segment_col", type="str", label="分段列名 (如时段/客群)", required=True),
            ParamSpec(name="n_bins", type="int", label="分箱数", default=10, min=2, max=50, advanced=True),
        ],
        cache=CacheConfig(),
        timeout_sec=120,
        estimated_duration_sec=5,
        tags=["metrics", "stability"],
        version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.metrics import csi, csi_table
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.metrics.csi 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "scores", "score_df"))
        score_col = params["score_col"]
        segment_col = params["segment_col"]
        for col in (score_col, segment_col):
            if col not in df.columns:
                raise FeatureNotFoundError(
                    f"列 {col} 不存在",
                    details={"node_type": self.contract.node_type, "missing_col": col},
                )
        segments = df.groupby(segment_col)
        sorted_keys = sorted(segments.groups.keys())
        if len(sorted_keys) < 2:
            raise ValidationError(
                f"分段列 {segment_col} 至少需要 2 个段",
                details={"node_type": self.contract.node_type},
            )

        expected = segments.get_group(sorted_keys[0])[score_col].astype(float).values
        actual = pd.concat(
            [segments.get_group(k)[score_col] for k in sorted_keys[1:]]
        ).astype(float).values
        n_bins = int(params.get("n_bins", 10))

        try:
            csi_value = float(csi(expected, actual, max_n_bins=n_bins))
            csi_df = csi_table(expected, actual, max_n_bins=n_bins)
        except Exception as e:
            raise ValidationError(
                f"CSI 计算失败: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        return {"csi_value": csi_value, "csi_table": csi_df}