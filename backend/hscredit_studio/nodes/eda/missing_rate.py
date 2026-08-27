"""缺失率分析 — 各字段缺失比例 + 缺失模式.

直接计算 DataFrame 每列的 ``isna()`` 比例与计数,
并按 ``threshold`` 阈值标记「是否高缺失」列。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hscredit_studio.core.exceptions import ValidationError
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.nodes.registry import register_node
from hscredit_studio.schemas.node_contract import (
    CacheConfig,
    NodeContract,
    ParamSpec,
    PortSchema,
)


@register_node
class MissingRateNode(BaseNode):
    """计算每列的缺失率."""

    contract = NodeContract(
        node_type="missing_rate",
        category="EDA",
        name="缺失率分析",
        description="统计每列的缺失率",
        icon="❓",
        inputs=[PortSchema(name="df", type="DataFrame", required=True)],
        outputs=[
            PortSchema(
                name="missing_df",
                type="DataFrame",
                description="含「字段名」「缺失数」「缺失率」「是否高缺失」的表",
            ),
            PortSchema(name="df", type="DataFrame", description="原始 DataFrame"),
        ],
        params=[
            ParamSpec(
                name="threshold",
                type="float",
                label="高缺失率阈值",
                default=0.5,
                min=0.0,
                max=1.0,
                step=0.05,
                advanced=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=120,
        estimated_duration_sec=10,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        df = inputs["df"]
        if not isinstance(df, pd.DataFrame):
            raise ValidationError(
                "输入必须为 pandas DataFrame",
                details={"node_type": self.contract.node_type, "actual_type": type(df).__name__},
            )
        n = len(df)
        threshold = float(params.get("threshold", 0.5))
        missing_count = df.isna().sum()
        missing_rate = missing_count / max(n, 1)
        missing_df = pd.DataFrame(
            {
                "字段名": missing_count.index.astype(str),
                "缺失数": missing_count.values,
                "缺失率": missing_rate.values,
                "是否高缺失": missing_rate.values >= threshold,
            }
        ).sort_values("缺失率", ascending=False)
        return {"missing_df": missing_df, "df": df}
