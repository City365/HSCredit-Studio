"""样本切分 — Train/Test + OOT 拆分.

OOT 拆分支持两种模式:

- 指定 ``oot_time_col``: 按该列升序排序, 取最早 N% 作为 OOT。
- 未指定: 按 ``stratify`` 字段随机抽样 ``oot_size`` 比例作为 OOT。
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from sklearn.model_selection import train_test_split

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
class TrainOOTSplitNode(BaseNode):
    """样本切分 — Train/Test 随机切分 + OOT 按时间切分."""

    contract = NodeContract(
        node_type="train_oot_split",
        category="数据接入",
        name="样本切分",
        description="将数据切分为训练集、测试集、OOT 集",
        icon="✂️",
        inputs=[PortSchema(name="df", type="DataFrame", required=True)],
        outputs=[
            PortSchema(name="train_df", type="DataFrame", description="训练集"),
            PortSchema(name="test_df", type="DataFrame", description="测试集"),
            PortSchema(name="oot_df", type="DataFrame", description="OOT 集（跨时间验证集）"),
        ],
        params=[
            ParamSpec(name="target", type="str", label="目标列", required=True),
            ParamSpec(
                name="test_size",
                type="float",
                label="测试集比例",
                default=0.2,
                min=0.05,
                max=0.5,
                step=0.05,
            ),
            ParamSpec(
                name="oot_size",
                type="float",
                label="OOT 比例",
                default=0.0,
                min=0.0,
                max=0.5,
                step=0.05,
            ),
            ParamSpec(
                name="oot_time_col",
                type="str",
                label="OOT 时间列（按此列升序取前 N%）",
                default="",
                advanced=True,
            ),
            ParamSpec(name="random_state", type="int", label="随机种子", default=42),
            ParamSpec(
                name="stratify",
                type="bool",
                label="分层切分",
                default=True,
            ),
        ],
        cache=CacheConfig(strategy="by_inputs_hash"),
        timeout_sec=300,
        estimated_duration_sec=30,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        df = inputs["df"]
        target = params["target"]
        if target not in df.columns:
            raise ValidationError(
                f"目标列 {target} 不在数据中",
                details={
                    "node_type": self.contract.node_type,
                    "target": target,
                    "columns": df.columns.tolist(),
                },
            )

        # 先做 OOT 切分（按时间或随机）
        oot_size = float(params.get("oot_size", 0.0) or 0.0)
        rest_df: pd.DataFrame = df
        oot_df: pd.DataFrame = df.iloc[0:0].copy()
        if oot_size > 0:
            oot_time_col = params.get("oot_time_col") or None
            if oot_time_col and oot_time_col in df.columns:
                df_sorted = df.sort_values(oot_time_col)
                oot_count = max(1, int(len(df) * oot_size))
                oot_df = df_sorted.iloc[:oot_count].copy()
                rest_df = df_sorted.iloc[oot_count:].copy()
            else:
                stratify = df[target] if params.get("stratify") else None
                if stratify is not None and stratify.nunique() < 2:
                    stratify = None
                rest_df, oot_df = train_test_split(
                    df,
                    test_size=oot_size,
                    random_state=params["random_state"],
                    stratify=stratify,
                )

        # 再做 Train/Test 切分
        stratify_train = rest_df[target] if params.get("stratify") and len(rest_df) > 0 else None
        if stratify_train is not None and stratify_train.nunique() < 2:
            stratify_train = None
        train_df, test_df = train_test_split(
            rest_df,
            test_size=params["test_size"],
            random_state=params["random_state"],
            stratify=stratify_train,
        )
        return {"train_df": train_df, "test_df": test_df, "oot_df": oot_df}
