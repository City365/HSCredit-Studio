"""IV 有效性分析 — 评估特征预测能力.

复用 ``hscredit.core.eda.relationship.iv_analysis``(导入失败时降级为本地实现):

- 计算单特征相对二分类目标的 IV 值。
- 给出中文预测能力评级(极强/强/中等/弱/极弱/无)。
- 单特征报错时,记录失败原因而非中断整批分析。
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from hscredit_studio.core.exceptions import DependencyError, ValidationError
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.nodes.registry import register_node
from hscredit_studio.schemas.node_contract import (
    CacheConfig,
    NodeContract,
    ParamSpec,
    PortSchema,
)


def _rate_iv(iv_value: float) -> str:
    """IV 值中文评级."""
    if iv_value >= 0.5:
        return "极强"
    if iv_value >= 0.3:
        return "强"
    if iv_value >= 0.1:
        return "中等"
    if iv_value >= 0.02:
        return "弱"
    return "极弱/无"


def _fallback_iv(x: pd.Series, y: pd.Series, max_n_bins: int = 5) -> float:
    """本地降级 IV 计算 — 等频分箱 + WOE 求和.

    仅在 hscredit 不可用时启用, 优先级低于 :func:`hs_iv_analysis`.
    """
    s = pd.Series(x).reset_index(drop=True)
    yy = pd.Series(y).reset_index(drop=True)
    df = pd.concat([s.rename("x"), yy.rename("y")], axis=1).dropna()
    if df["y"].nunique() < 2 or df["x"].nunique() < 2:
        return 0.0

    n_bins = min(max_n_bins, max(2, df["x"].nunique()))
    try:
        df["bin"] = pd.qcut(df["x"], q=n_bins, duplicates="drop")
    except ValueError:
        df["bin"] = pd.cut(df["x"], bins=n_bins)

    grouped = df.groupby("bin", observed=True)
    total_bad = float((df["y"] == 1).sum()) or 1.0
    total_good = float((df["y"] == 0).sum()) or 1.0
    iv_total = 0.0
    for _, sub in grouped:
        bad = max(float((sub["y"] == 1).sum()), 0.5)
        good = max(float((sub["y"] == 0).sum()), 0.5)
        iv_total += (bad / total_bad - good / total_good) * np.log(
            (bad / total_bad) / (good / total_good)
        )
    return float(iv_total)


class _HsIvAdapter:
    """适配 ``hscredit.core.eda.relationship.iv_analysis`` 两种签名.

    该函数返回 dict ``{"IV值": float, ...}``;若失败则回退到本地等频分箱实现。
    """

    def __init__(self) -> None:
        self._fn = None
        try:
            from hscredit.core.eda.relationship import iv_analysis as hs_iv_analysis

            self._fn = hs_iv_analysis
        except (ImportError, AttributeError):
            self._fn = None

    def compute(self, df: pd.DataFrame, feature: str, target: str, max_n_bins: int) -> float | None:
        if self._fn is None:
            return _fallback_iv(df[feature], df[target], max_n_bins=max_n_bins)
        try:
            result = self._fn(df, feature=feature, target=target, n_bins=max_n_bins)
            if isinstance(result, dict) and "IV值" in result:
                return float(result["IV值"])
            if isinstance(result, (tuple, list)) and len(result) >= 1:
                return float(result[0])
        except Exception:
            return _fallback_iv(df[feature], df[target], max_n_bins=max_n_bins)
        return None


_IV_ADAPTER = _HsIvAdapter()


@register_node
class IVAnalysisNode(BaseNode):
    """计算每个特征相对于目标的 IV 值."""

    contract = NodeContract(
        node_type="iv_analysis",
        category="EDA",
        name="IV 有效性分析",
        description="计算特征 IV 值，评估预测能力",
        icon="📊",
        inputs=[PortSchema(name="df", type="DataFrame", required=True)],
        outputs=[
            PortSchema(
                name="iv_df",
                type="DataFrame",
                description="含「特征名」「IV值」「预测力」的表",
            ),
            PortSchema(name="df", type="DataFrame", description="原始 DataFrame"),
        ],
        params=[
            ParamSpec(name="target", type="str", label="目标列名", required=True),
            ParamSpec(
                name="features",
                type="list",
                label="特征列表（不指定则全部分析）",
                default=[],
                advanced=True,
            ),
            ParamSpec(
                name="max_n_bins",
                type="int",
                label="最大分箱数",
                default=5,
                min=2,
                max=10,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=300,
        estimated_duration_sec=30,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        df = inputs["df"]
        if not isinstance(df, pd.DataFrame):
            raise ValidationError(
                "输入必须为 pandas DataFrame",
                details={"node_type": self.contract.node_type, "actual_type": type(df).__name__},
            )
        target = params["target"]
        if target not in df.columns:
            raise ValidationError(
                f"目标列 {target} 不在数据中",
                details={"node_type": self.contract.node_type, "target": target},
            )
        if df[target].nunique() < 2:
            raise ValidationError(
                f"目标列 {target} 需要至少 2 个类别",
                details={"node_type": self.contract.node_type, "target": target},
            )

        features = params.get("features") or [c for c in df.columns if c != target]
        if not isinstance(features, list):
            features = list(features)
        max_n_bins = int(params.get("max_n_bins", 5))

        results: list[dict[str, Any]] = []
        for feat in features:
            if feat not in df.columns:
                results.append(
                    {"特征名": feat, "IV值": None, "预测力": f"特征不存在: {feat}"}
                )
                continue
            try:
                iv_value = _IV_ADAPTER.compute(df, feat, target, max_n_bins)
                if iv_value is None:
                    results.append(
                        {"特征名": feat, "IV值": None, "预测力": "分析失败"}
                    )
                else:
                    results.append(
                        {
                            "特征名": feat,
                            "IV值": round(iv_value, 4),
                            "预测力": _rate_iv(iv_value),
                        }
                    )
            except Exception as e:  # noqa: BLE001
                results.append(
                    {
                        "特征名": feat,
                        "IV值": None,
                        "预测力": f"分析失败: {type(e).__name__}: {e}",
                    }
                )

        iv_df = pd.DataFrame(results).sort_values(
            "IV值", ascending=False, na_position="last"
        )
        return {"iv_df": iv_df, "df": df}
