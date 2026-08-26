"""Excel 文件接入节点."""
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
    ParamSpec,
    PortSchema,
)


@register_node
class ExcelIngestNode(BaseNode):
    """从 Excel 文件读取数据.

    inputs: 无（数据源节点）
    outputs: df (DataFrame), schema (字段类型推断结果)
    params: path, sheet_name, header
    """

    contract = NodeContract(
        node_type="excel_ingest",
        category="数据接入",
        name="Excel 文件接入",
        description="从 Excel 文件读取数据集",
        icon="📊",
        inputs=[],
        outputs=[
            PortSchema(name="df", type="DataFrame", description="读取的 DataFrame"),
            PortSchema(name="schema", type="JSON", description="字段类型推断结果"),
        ],
        params=[
            ParamSpec(
                name="path",
                type="file",
                label="Excel 文件路径",
                required=True,
                placeholder="/data/train.xlsx",
            ),
            ParamSpec(
                name="sheet_name",
                type="str",
                label="Sheet 名",
                default="Sheet1",
            ),
            ParamSpec(
                name="header",
                type="int",
                label="表头行号",
                default=0,
                min=0,
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
                "必须提供 Excel 文件路径",
                details={"node_type": self.contract.node_type},
            )
        if not os.path.exists(path):
            raise ValidationError(
                f"Excel 文件不存在: {path}",
                details={"node_type": self.contract.node_type, "path": path},
            )
        sheet_name = params.get("sheet_name", "Sheet1") or 0
        header = params.get("header", 0)
        df = pd.read_excel(path, sheet_name=sheet_name, header=header)
        schema = {str(col): str(dtype) for col, dtype in df.dtypes.items()}
        return {"df": df, "schema": schema}
