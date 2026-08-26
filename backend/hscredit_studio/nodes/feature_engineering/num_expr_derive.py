"""表达式特征衍生 — 通过 numexpr/pandas 表达式批量衍生新特征.

复用 ``hscredit.core.feature_engineering.NumExprDerive``。
``expressions`` 参数支持两种传入形式:

- ``list[tuple[str, str]]``: 标准格式,如 ``[("ratio", "a / b")]``。
- ``str``: 多行文本,每行 ``新列名 = 表达式``,如 ``"ratio = a / b\\nflag = a > 0"``。
"""
from __future__ import annotations

from typing import Any

import pandas as pd

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


def _parse_expressions(raw: Any) -> list[tuple[str, str]]:
    """支持 list[tuple] 与 str(``name = expr`` 多行)两种形式."""
    if isinstance(raw, str):
        rules: list[tuple[str, str]] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                raise ValidationError(
                    f"表达式行格式错误,缺少 '=': {line!r}",
                    details={"line": line},
                )
            name, expr = stripped.split("=", 1)
            rules.append((name.strip(), expr.strip()))
        if not rules:
            raise ValidationError(
                "expressions 至少需要一条规则",
                details={"raw": raw},
            )
        return rules
    if isinstance(raw, list):
        rules = []
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                rules.append((str(item[0]), str(item[1])))
            elif isinstance(item, str) and "=" in item:
                name, expr = item.split("=", 1)
                rules.append((name.strip(), expr.strip()))
            else:
                raise ValidationError(
                    f"表达式元素必须是 [name, expr] 二元组或 'name=expr' 字符串: {item!r}",
                    details={"item": item},
                )
        return rules
    raise ValidationError(
        "expressions 必须是 list 或 str",
        details={"actual_type": type(raw).__name__},
    )


@register_node
class NumExprDeriveNode(BaseNode):
    """通过数学表达式衍生新特征."""

    contract = NodeContract(
        node_type="num_expr_derive",
        category="特征工程",
        name="表达式特征衍生",
        description="用 numexpr/pandas 表达式批量衍生新特征",
        icon="➕",
        inputs=[PortSchema(name="df", type="DataFrame", required=True)],
        outputs=[
            PortSchema(name="df", type="DataFrame", description="含新衍生列的 DataFrame")
        ],
        params=[
            ParamSpec(
                name="expressions",
                type="list",
                label="表达式列表（[新列名, 表达式]）",
                required=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=300,
        estimated_duration_sec=20,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        try:
            from hscredit.core.feature_engineering import NumExprDerive
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.feature_engineering.NumExprDerive 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        df = inputs["df"]
        rules = _parse_expressions(params.get("expressions"))

        try:
            deriver = NumExprDerive(derivings=rules)
        except (TypeError, ValueError) as e:
            raise ValidationError(
                f"构造 NumExprDerive 失败: {e}",
                details={"node_type": self.contract.node_type, "rules": rules},
            ) from e

        try:
            result_df = deriver.fit_transform(df)
        except Exception as e:
            raise ValidationError(
                f"表达式衍生执行失败: {e}",
                details={"node_type": self.contract.node_type, "rules": rules},
            ) from e
        return {"df": result_df}
