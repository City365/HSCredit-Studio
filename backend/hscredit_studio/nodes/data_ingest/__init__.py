"""数据接入类节点 — 文件读取、样本切分、字段类型推断.

导入本包会触发各节点模块的 ``@register_node`` 装饰器,
把节点类注册到 :class:`hscredit_studio.nodes.registry.NodeRegistry`.
"""
from __future__ import annotations

from hscredit_studio.nodes.data_ingest import (
    csv_ingest,
    excel_ingest,
    field_type_infer,
    train_oot_split,
)

__all__ = [
    "csv_ingest",
    "excel_ingest",
    "train_oot_split",
    "field_type_infer",
]
