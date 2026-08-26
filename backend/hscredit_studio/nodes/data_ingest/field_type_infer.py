"""字段类型推断 — 自动识别数值/类别/日期/ID 列.

推断规则:

1. 唯一值比例 >= ``id_threshold_unique_ratio`` 且样本数 > 1 → ``id``
2. dtype 为 int/float/bool → ``numeric`` / ``boolean``
3. dtype 为 datetime → ``datetime``
4. 否则尝试 ``pd.to_datetime`` 解析;解析成功率 >= ``date_min_parse_ratio`` → ``datetime``
5. 其余 → ``categorical``
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
class FieldTypeInferNode(BaseNode):
    """推断 DataFrame 中每个字段的类型（数值型/类别型/日期型/ID型）."""

    contract = NodeContract(
        node_type="field_type_infer",
        category="数据接入",
        name="字段类型推断",
        description="自动推断每列的数据类型",
        icon="🔍",
        inputs=[PortSchema(name="df", type="DataFrame", required=True)],
        outputs=[
            PortSchema(name="schema", type="JSON", description="字段类型映射表"),
            PortSchema(name="df", type="DataFrame", description="原始 DataFrame（透传）"),
        ],
        params=[
            ParamSpec(
                name="id_threshold_unique_ratio",
                type="float",
                label="ID 列唯一值比例阈值",
                default=0.95,
                min=0.5,
                max=1.0,
                step=0.05,
                advanced=True,
            ),
            ParamSpec(
                name="date_min_parse_ratio",
                type="float",
                label="日期解析成功率阈值",
                default=0.8,
                min=0.5,
                max=1.0,
                step=0.05,
                advanced=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=120,
        estimated_duration_sec=15,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        df = inputs["df"]
        if not isinstance(df, pd.DataFrame):
            raise ValidationError(
                "输入必须为 pandas DataFrame",
                details={
                    "node_type": self.contract.node_type,
                    "actual_type": type(df).__name__,
                },
            )

        id_threshold = float(params.get("id_threshold_unique_ratio", 0.95))
        date_threshold = float(params.get("date_min_parse_ratio", 0.8))
        n = len(df)

        schema: dict[str, str] = {}
        for col in df.columns:
            s = df[col]
            dtype = str(s.dtype)
            unique_ratio = (s.nunique(dropna=False) / max(n, 1)) if n > 0 else 0.0

            if n > 1 and unique_ratio >= id_threshold:
                schema[str(col)] = "id"
            elif dtype == "bool":
                schema[str(col)] = "boolean"
            elif dtype.startswith("int") or dtype.startswith("float"):
                schema[str(col)] = "numeric"
            elif dtype.startswith("datetime"):
                schema[str(col)] = "datetime"
            else:
                try:
                    parsed = pd.to_datetime(s, errors="coerce", format="mixed")
                    non_null_ratio = float(parsed.notna().sum()) / max(n, 1)
                    if non_null_ratio >= date_threshold:
                        schema[str(col)] = "datetime"
                    else:
                        schema[str(col)] = "categorical"
                except (ValueError, TypeError):
                    schema[str(col)] = "categorical"
        return {"schema": schema, "df": df}
