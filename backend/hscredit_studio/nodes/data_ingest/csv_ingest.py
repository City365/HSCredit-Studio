"""CSV 文件接入节点."""
from __future__ import annotations

import os
from typing import Any

import pandas as pd

from hscredit_studio.core.exceptions import ValidationError
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
class CSVIngestNode(BaseNode):
    """从 CSV 文件读取数据.

    inputs: 无（数据源节点）
    outputs: df (DataFrame), schema (字段类型推断结果)
    params: path (文件路径), sep, encoding, nrows
    """

    contract = NodeContract(
        node_type="csv_ingest",
        category="数据接入",
        name="CSV 文件接入",
        description="从 CSV 文件读取数据集",
        icon="📥",
        inputs=[],
        outputs=[
            PortSchema(name="df", type="DataFrame", description="读取的 DataFrame"),
            PortSchema(name="schema", type="JSON", description="字段类型推断结果"),
        ],
        params=[
            ParamSpec(
                name="path",
                type="file",
                label="CSV 文件路径",
                required=True,
                placeholder="/data/train.csv",
            ),
            ParamSpec(
                name="sep",
                type="str",
                label="分隔符",
                default=",",
                choices=[
                    ParamChoice(label="逗号 ,", value=","),
                    ParamChoice(label="制表符 \\t", value="\t"),
                    ParamChoice(label="分号 ;", value=";"),
                ],
            ),
            ParamSpec(
                name="encoding",
                type="str",
                label="编码",
                default="utf-8",
                choices=[
                    ParamChoice(label="UTF-8", value="utf-8"),
                    ParamChoice(label="GBK", value="gbk"),
                    ParamChoice(label="GB18030", value="gb18030"),
                ],
            ),
            ParamSpec(
                name="nrows",
                type="int",
                label="读取行数限制",
                default=None,
                advanced=True,
                min=1,
            ),
        ],
        cache=CacheConfig(strategy="by_inputs_hash"),
        timeout_sec=600,
        estimated_duration_sec=60,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        path = params.get("path")
        if not path:
            raise ValidationError(
                "必须提供 CSV 文件路径",
                details={"node_type": self.contract.node_type},
            )
        if not os.path.exists(path):
            raise ValidationError(
                f"CSV 文件不存在: {path}",
                details={"node_type": self.contract.node_type, "path": path},
            )
        df = pd.read_csv(
            path,
            sep=params.get("sep", ","),
            encoding=params.get("encoding", "utf-8"),
            nrows=params.get("nrows"),
        )
        schema = {str(col): str(dtype) for col, dtype in df.dtypes.items()}
        return {"df": df, "schema": schema}
