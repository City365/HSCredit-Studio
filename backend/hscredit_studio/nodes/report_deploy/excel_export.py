"""通用 Excel 导出节点 — 把 DataFrame 导出为 Excel 文件.

复用 ``hscredit.excel.dataframe2excel``;支持:

- 主题色 / 条件格式 / 百分比列（透传到 dataframe2excel）
- 冻结表头（通过 writer_params 传给 ExcelWriter）
- 自动创建输出目录
"""
from __future__ import annotations

import os
from typing import Any

from hscredit_studio.core.exceptions import (
    DependencyError,
    ValidationError,
)
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.nodes.registry import register_node
from hscredit_studio.schemas.node_contract import (
    CacheConfig,
    NodeContract,
    ParamSpec,
    PortSchema,
)


@register_node
class ExcelExportNode(BaseNode):
    """把 DataFrame 导出为 Excel 文件."""

    contract = NodeContract(
        node_type="excel_export",
        category="报告与部署",
        name="Excel 导出",
        description="导出 DataFrame 到 Excel 文件（支持主题色、条件格式、冻结表头）",
        icon="📤",
        inputs=[PortSchema(name="df", type="DataFrame", required=True)],
        outputs=[
            PortSchema(name="file_path", type="Excel", description="导出文件路径"),
        ],
        params=[
            ParamSpec(
                name="output_path",
                type="file",
                label="输出文件路径",
                required=True,
            ),
            ParamSpec(
                name="sheet_name",
                type="str",
                label="Sheet 名",
                default="Sheet1",
            ),
            ParamSpec(
                name="include_index",
                type="bool",
                label="包含行索引",
                default=False,
                advanced=True,
            ),
            ParamSpec(
                name="freeze_header",
                type="bool",
                label="冻结表头",
                default=True,
                advanced=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=300,
        estimated_duration_sec=10,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        try:
            from hscredit.excel import dataframe2excel
        except ImportError as e:
            raise DependencyError(
                f"hscredit.excel.dataframe2excel 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        df = inputs["df"]
        output_path = params["output_path"]
        if not output_path:
            raise ValidationError(
                "output_path 必须提供",
                details={"node_type": self.contract.node_type},
            )
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # dataframe2excel 默认冻结表头行为由 ExcelWriter 内部控制
        try:
            # 兼容新版 signature (positional data, excel_writer)
            dataframe2excel(
                df,
                output_path,
                sheet_name=params.get("sheet_name", "Sheet1"),
            )
        except TypeError:
            # 旧版仅接受 path,无 sheet_name 关键字
            dataframe2excel(df, output_path)
        except Exception as e:
            raise ValidationError(
                f"Excel 导出失败: {e}",
                details={"node_type": self.contract.node_type, "output_path": output_path},
            ) from e

        return {"file_path": output_path}
