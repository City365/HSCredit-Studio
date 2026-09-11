"""EDA 节点族 — 3 个数据探索节点 (Phase 6 B36 阶段 3.3).

封装 hscredit.core.eda 的核心函数:

- ``eda_overview`` — :func:`data_quality_report` 综合数据质量报告
- ``eda_correlation`` — :func:`high_correlation_pairs` 高相关性特征对
- ``eda_population_stability`` — :func:`population_stability_monitor` 跨期客群稳定性
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hscredit_studio.core.exceptions import (
    DependencyError,
    ValidationError,
)
from hscredit_studio.nodes._common import coerce_features_param, resolve_dataframe_input
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.nodes.registry import register_node
from hscredit_studio.schemas.node_contract import (
    CacheConfig,
    NodeContract,
    ParamChoice,
    ParamSpec,
    PortSchema,
)


# ===== 1. 数据质量报告 =====


@register_node
class EdaOverviewNode(BaseNode):
    contract = NodeContract(
        node_type="eda_overview",
        category="EDA",
        name="数据质量报告",
        description="综合数据质量报告 (缺失率/常数列/唯一值数/类型)",
        icon="📋",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["selected_df", "woe_df", "binned_df"])],
        outputs=[
            PortSchema(name="report", type="DataFrame", description="数据质量报告 DataFrame"),
            PortSchema(name="data_info", type="DataFrame", description="数据基本信息 (行/列/类型)"),
        ],
        params=[
            ParamSpec(name="features", type="list", label="特征列表 (留空=全部)", default=[]),
            ParamSpec(name="missing_threshold", type="float", label="缺失率告警阈值",
                      default=0.5, min=0.0, max=1.0, advanced=True),
            ParamSpec(name="constant_threshold", type="float", label="常数列阈值 (top-N 占比)",
                      default=0.95, min=0.5, max=1.0, advanced=True),
        ],
        cache=CacheConfig(), timeout_sec=120, estimated_duration_sec=10,
        tags=["eda"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.eda import data_quality_report, data_info
        except ImportError as e:
            raise DependencyError(f"hscredit.core.eda.data_quality_report 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        df = resolve_dataframe_input(inputs, self.contract.node_type,
                                     aliases=("df", "selected_df", "woe_df", "binned_df"))
        features = params.get("features") or []
        if isinstance(features, str):
            features = [f.strip() for f in features.split(",") if f.strip()]
        if features:
            coerce_features_param(features, list(df.columns), self.contract.node_type)
        try:
            report = data_quality_report(
                df,
                features=features or None,
                missing_threshold=float(params.get("missing_threshold", 0.5)),
                constant_threshold=float(params.get("constant_threshold", 0.95)),
            )
            info = data_info(df)
        except Exception as e:
            raise ValidationError(f"data_quality_report 失败: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        return {"report": report, "data_info": info}


# ===== 2. 高相关性特征对 =====


@register_node
class EdaCorrelationNode(BaseNode):
    contract = NodeContract(
        node_type="eda_correlation",
        category="EDA",
        name="高相关性特征对",
        description="检测高相关性特征对 (|r| >= threshold), 用于共线性诊断",
        icon="🔗",
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["woe_df", "selected_df"])],
        outputs=[PortSchema(name="pairs", type="DataFrame", description="高相关对 DataFrame")],
        params=[
            ParamSpec(name="features", type="list", label="特征列表 (留空=全部数值列)", default=[]),
            ParamSpec(name="threshold", type="float", label="相关性阈值 (|r| >=)",
                      default=0.8, min=0.0, max=1.0),
            ParamSpec(name="method", type="select", label="相关系数",
                      default="pearson",
                      choices=[ParamChoice(label="pearson", value="pearson"),
                               ParamChoice(label="spearman", value="spearman"),
                               ParamChoice(label="kendall", value="kendall")]),
        ],
        cache=CacheConfig(), timeout_sec=120, estimated_duration_sec=5,
        tags=["eda"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.eda import high_correlation_pairs
        except ImportError as e:
            raise DependencyError(f"hscredit.core.eda.high_correlation_pairs 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df", "woe_df", "selected_df"))
        features = params.get("features") or []
        if isinstance(features, str):
            features = [f.strip() for f in features.split(",") if f.strip()]
        if features:
            coerce_features_param(features, list(df.columns), self.contract.node_type)
        try:
            pairs = high_correlation_pairs(
                df,
                features=features or None,
                threshold=float(params.get("threshold", 0.8)),
                method=params.get("method", "pearson"),
            )
        except Exception as e:
            raise ValidationError(f"high_correlation_pairs 失败: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        return {"pairs": pairs}


# ===== 3. 跨期客群稳定性 =====


@register_node
class EdaPopulationStabilityNode(BaseNode):
    contract = NodeContract(
        node_type="eda_population_stability",
        category="EDA",
        name="跨期客群稳定性",
        description="客群分布跨期稳定性监控 (PSI 风格, 跨时间/分组)",
        icon="📊",
        inputs=[PortSchema(name="df", type="DataFrame", required=True)],
        outputs=[PortSchema(name="report", type="DataFrame", description="跨期稳定性报告")],
        params=[
            ParamSpec(name="segment_col", type="str", label="客群分段列 (必填)", required=True),
            ParamSpec(name="features", type="list", label="特征列表 (留空=全部数值列)", default=[]),
            ParamSpec(name="date_col", type="str", label="日期列 (可选)", required=False, advanced=True),
            ParamSpec(name="group_col", type="str", label="队列列 (可选)", required=False, advanced=True),
            ParamSpec(name="n_bins", type="int", label="分箱数", default=5, min=2, max=20, advanced=True),
            ParamSpec(name="binning_method", type="select", label="分箱方法",
                      default="quantile",
                      choices=[ParamChoice(label="quantile", value="quantile"),
                               ParamChoice(label="uniform", value="uniform"),
                               ParamChoice(label="tree", value="tree")],
                      advanced=True),
        ],
        cache=CacheConfig(), timeout_sec=300, estimated_duration_sec=20,
        tags=["eda", "stability"], version="1.0.0",
    )

    def run(self, inputs, params):
        try:
            from hscredit.core.eda import population_stability_monitor
        except ImportError as e:
            raise DependencyError(f"hscredit.core.eda.population_stability_monitor 不可用: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        df = resolve_dataframe_input(inputs, self.contract.node_type, aliases=("df",))
        segment_col = params.get("segment_col")
        if not segment_col or segment_col not in df.columns:
            raise ValidationError(f"segment_col '{segment_col}' 不存在",
                                  details={"node_type": self.contract.node_type})
        # expected = 第一段, actual = 其余段
        sorted_groups = sorted(df[segment_col].unique())
        if len(sorted_groups) < 2:
            raise ValidationError(f"segment_col '{segment_col}' 至少需要 2 个分组",
                                  details={"node_type": self.contract.node_type})
        expected = df[df[segment_col] == sorted_groups[0]].drop(columns=[segment_col])
        actual = df[df[segment_col].isin(sorted_groups[1:])].drop(columns=[segment_col])

        features = params.get("features") or []
        if isinstance(features, str):
            features = [f.strip() for f in features.split(",") if f.strip()]
        if features:
            coerce_features_param(features, list(df.columns), self.contract.node_type)

        try:
            report = population_stability_monitor(
                expected,
                actual,
                segment_cols=params.get("features") or list(expected.select_dtypes(include="number").columns),
                n_bins=int(params.get("n_bins", 5)),
                binning_method=params.get("binning_method", "quantile"),
                date_col=params.get("date_col"),
                group_col=params.get("group_col"),
            )
        except Exception as e:
            raise ValidationError(f"population_stability_monitor 失败: {e}",
                                  details={"node_type": self.contract.node_type}) from e
        return {"report": report}