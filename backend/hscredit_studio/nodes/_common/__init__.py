"""节点包内通用工具.

集中放置跨节点复用的小工具, 避免每个节点文件重复样板代码:

- :data:`TARGET_PARAM` — 工作流级目标特征参数模板
- :func:`target_param` — 工厂方法, 生成同名 ParamSpec
- :func:`resolve_dataframe_input` — 在多别名端口中找第一个 DataFrame
- :func:`coerce_features_param` — 把 list/逗号字符串统一成 list[str]
"""

from __future__ import annotations

from typing import Any

from hscredit_studio.schemas.node_contract import ParamSpec


# ===== target 参数模板 =====


def target_param(
    label: str = "目标列名",
    description: str = "建模目标 (Y) 列名, 通常工作流级统一管理",
    required: bool = True,
) -> ParamSpec:
    """生成工作流级 ``target`` 参数规格.

    所有需要目标列的节点 (分箱/编码/筛选/模型) 都复用此模板,
    避免重复 ``workflow_scoped=True`` 这种关键 flag.
    """
    return ParamSpec(
        name="target",
        type="str",
        label=label,
        description=description,
        required=required,
        workflow_scoped=True,
    )


# 向后兼容: 也保留模块级常量
TARGET_PARAM = target_param()


# ===== DataFrame 输入解析 =====


def resolve_dataframe_input(
    inputs: dict[str, Any],
    node_type: str,
    aliases: tuple[str, ...] = ("df",),
) -> Any:
    """从 inputs 中按 aliases 顺序找第一个 DataFrame.

    处理: 单值 / list 合并 (executor 合并多 df 时可能产出 list).
    找不到时抛 :class:`ValidationError`.
    """
    from hscredit_studio.core.exceptions import ValidationError

    for key in aliases:
        if key not in inputs:
            continue
        value = inputs[key]
        if value is None:
            continue
        # executor 合并多同名端口时输出 list
        if isinstance(value, list):
            if not value:
                continue
            merged = value[0]
            for extra in value[1:]:
                # 合并所有 *_bin 列等额外列
                try:
                    for col in extra.columns:
                        if col not in merged.columns:
                            merged = merged.copy()
                            merged[col] = extra[col]
                except AttributeError:
                    continue
            return merged
        return value
    raise ValidationError(
        f"节点 {node_type} 缺少 DataFrame 输入 (尝试 {list(aliases)})",
        details={
            "node_type": node_type,
            "available_inputs": list(inputs.keys()),
            "aliases": list(aliases),
        },
    )


# ===== 特征列表规范化 =====


def coerce_features_param(
    value: Any,
    df_columns: list[str],
    node_type: str,
) -> list[str]:
    """把 list / 逗号字符串 / None 统一为 list[str], 并校验全部存在."""
    from hscredit_studio.core.exceptions import FeatureNotFoundError, ValidationError

    if value is None or value == "":
        raise ValidationError(
            f"节点 {node_type} 缺少必需参数 features",
            details={"node_type": node_type},
        )
    if isinstance(value, str):
        # 支持逗号分隔
        value = [v.strip() for v in value.split(",") if v.strip()]
    if not isinstance(value, (list, tuple)):
        raise ValidationError(
            f"节点 {node_type} 的 features 必须是列表或逗号分隔字符串",
            details={"node_type": node_type, "value": value},
        )
    features = [str(v) for v in value if v]
    if not features:
        raise ValidationError(
            f"节点 {node_type} 的 features 不能为空",
            details={"node_type": node_type},
        )
    missing = [f for f in features if f not in df_columns]
    if missing:
        raise FeatureNotFoundError(
            f"以下特征不在数据中: {missing}",
            details={
                "node_type": node_type,
                "missing_features": missing,
                "available_columns": df_columns,
            },
        )
    return features


__all__ = [
    "TARGET_PARAM",
    "coerce_features_param",
    "resolve_dataframe_input",
    "target_param",
]