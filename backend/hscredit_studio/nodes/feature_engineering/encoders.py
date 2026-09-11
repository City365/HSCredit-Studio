"""编码器节点族 — 5 种类别/数值特征编码 (Phase 6 B36).

封装 hscredit 的 5 种编码器:

- ``target_encoder`` — Target Encoder (平滑贝叶斯均值)
- ``count_encoder`` — Count/Frequency Encoder
- ``ordinal_encoder`` — Ordinal Encoder (序数映射)
- ``catboost_encoder`` — CatBoost Encoder (带噪声的 Target)
- ``one_hot_encoder`` — One-Hot Encoder (独热)

每种编码器都是 sklearn Transformer 风格, 都接受 ``cols`` 参数指定要编码的列.
fit 时需要 target (除 count/ordinal/one_hot 外), transform 返回编码后的 DataFrame.

约定:

- 输入: ``df`` (DataFrame)
- 输出: ``encoder`` (EncoderArtifact) + ``encoded_df`` (DataFrame, 编码列已替换)
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hscredit_studio.core.exceptions import (
    DependencyError,
    FeatureNotFoundError,
    ValidationError,
)
from hscredit_studio.nodes._common import coerce_features_param, resolve_dataframe_input
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.nodes.registry import register_node
from hscredit_studio.schemas.node_contract import (
    CacheConfig,
    NodeContract,
    ParamSpec,
    PortSchema,
)


# 通用 encoder contract 构造器
def _make_encoder_contract(
    node_type: str,
    name: str,
    description: str,
    icon: str,
    needs_target: bool = True,
    extra_params: list[ParamSpec] | None = None,
) -> NodeContract:
    params: list[ParamSpec] = [
        ParamSpec(
            name="features",
            type="list",
            label="要编码的特征列名",
            required=True,
            description="多个列用逗号分隔或传列表",
        ),
    ]
    if needs_target:
        from hscredit_studio.nodes._common import target_param

        params.append(target_param(label="目标列名 (仅 fit 时用)"))
    params.append(
        ParamSpec(
            name="drop_invariant",
            type="bool",
            label="丢弃常数列",
            default=False,
            advanced=True,
        )
    )
    if extra_params:
        params.extend(extra_params)
    return NodeContract(
        node_type=node_type,
        category="特征工程",
        name=name,
        description=description,
        icon=icon,
        inputs=[PortSchema(name="df", type="DataFrame", required=True, aliases=["woe_df", "binned_df", "selected_df"])],
        outputs=[
            PortSchema(name="encoder", type="EncoderArtifact", description="训练好的编码器"),
            PortSchema(name="encoded_df", type="DataFrame", description="编码后的 DataFrame"),
            PortSchema(name="df", type="DataFrame", description="= encoded_df (别名, 便于下游引用)"),
        ],
        params=params,
        cache=CacheConfig(),
        timeout_sec=300,
        estimated_duration_sec=20,
        tags=["encoder"],
        version="1.0.0",
    )


def _build_encoder_run(class_name: str, class_path: str, needs_target: bool):
    """生成 run() 闭包 (类 → 实例 → fit → transform 模式)."""
    def run(self, inputs, params):
        try:
            import importlib

            mod = importlib.import_module(class_path)
            encoder_cls = getattr(mod, class_name)
        except (ImportError, AttributeError) as e:
            raise DependencyError(
                f"{class_path}.{class_name} 不可用: {e}",
                details={"node_type": self.contract.node_type, "encoder_class": class_name},
            ) from e

        df = resolve_dataframe_input(
            inputs, self.contract.node_type, aliases=("df", "woe_df", "binned_df", "selected_df")
        )
        features = coerce_features_param(params.get("features"), list(df.columns), self.contract.node_type)

        encoder_kwargs: dict[str, Any] = {
            "cols": features,
            "drop_invariant": bool(params.get("drop_invariant", False)),
            "return_df": True,
        }

        # 注入额外参数 (除 features/drop_invariant 外)
        for key, value in params.items():
            if key in ("features", "drop_invariant", "target"):
                continue
            encoder_kwargs[key] = value

        # 需要 target 的编码器
        if needs_target:
            target = params.get("target")
            if not target:
                raise ValidationError(
                    f"节点 {self.contract.node_type} 需要 target 参数",
                    details={"node_type": self.contract.node_type},
                )
            if target not in df.columns:
                raise FeatureNotFoundError(
                    f"目标列 {target} 不存在",
                    details={"node_type": self.contract.node_type, "target": target},
                )
            encoder_kwargs["target"] = target

        try:
            encoder = encoder_cls(**encoder_kwargs)
        except TypeError as e:
            raise ValidationError(
                f"构造编码器 {class_name} 失败: {e}",
                details={
                    "node_type": self.contract.node_type,
                    "encoder_class": class_name,
                    "encoder_kwargs": {k: v for k, v in encoder_kwargs.items() if k not in ("cols",)},
                },
            ) from e

        try:
            if needs_target:
                # 同时传入 X 和 y
                encoder.fit(df[features], df[target])
            else:
                encoder.fit(df[features])
            encoded = encoder.transform(df[features])
        except Exception as e:
            raise ValidationError(
                f"{class_name} 编码失败: {e}",
                details={"node_type": self.contract.node_type, "features": features},
            ) from e

        # 拼接 target/非特征列保留
        keep_cols = [c for c in df.columns if c not in features]
        encoded_df = pd.concat(
            [encoded.reset_index(drop=True), df[keep_cols].reset_index(drop=True)],
            axis=1,
        )
        return {"encoder": encoder, "encoded_df": encoded_df, "df": encoded_df}

    return run


def _make_encoder_node(
    node_type: str,
    class_path: str,
    class_name: str,
    display_name: str,
    description: str,
    icon: str,
    needs_target: bool = True,
    extra_params: list[ParamSpec] | None = None,
):
    """为每个编码器生成独立节点类."""
    node_contract = _make_encoder_contract(
        node_type=node_type,
        name=display_name,
        description=description,
        icon=icon,
        needs_target=needs_target,
        extra_params=extra_params,
    )

    @register_node
    class _GeneratedNode(BaseNode):
        contract = node_contract

        # run 是闭包, 不能简单地设为方法属性 — 用 setattr 注入
        pass

    # 动态挂上 run 方法
    setattr(_GeneratedNode, "run", _build_encoder_run(class_name, class_path, needs_target))
    # 类型名称便于调试
    _GeneratedNode.__name__ = f"{node_type.replace('_', ' ').title().replace(' ', '')}Node"
    return _GeneratedNode


# ===== 5 个编码器节点 =====

TargetEncoderNode = _make_encoder_node(
    node_type="target_encoder",
    class_path="hscredit.core.encoders",
    class_name="TargetEncoder",
    display_name="Target 编码",
    description="目标均值编码, 监督式, 适合高基数类别特征",
    icon="🎯",
    needs_target=True,
    extra_params=[
        ParamSpec(name="smoothing", type="float", label="贝叶斯平滑系数", default=1.0, min=0.0, max=100.0, advanced=True),
        ParamSpec(name="min_samples_leaf", type="int", label="最小叶样本数", default=1, min=1, max=1000, advanced=True),
        ParamSpec(name="noise", type="float", label="高斯噪声 std", default=None, min=0.0, max=10.0, advanced=True),
    ],
)

CountEncoderNode = _make_encoder_node(
    node_type="count_encoder",
    class_path="hscredit.core.encoders",
    class_name="CountEncoder",
    display_name="频数编码",
    description="把类别值替换为出现频次 (或频率), 无监督",
    icon="🔢",
    needs_target=False,
    extra_params=[
        ParamSpec(
            name="normalize",
            type="bool",
            label="归一化为频率 (而非计数)",
            default=False,
            advanced=True,
        ),
        ParamSpec(
            name="min_group_size",
            type="int",
            label="低频合并阈值 (None 不合并)",
            default=None,
            min=1,
            max=10000,
            advanced=True,
        ),
    ],
)

OrdinalEncoderNode = _make_encoder_node(
    node_type="ordinal_encoder",
    class_path="hscredit.core.encoders",
    class_name="OrdinalEncoder",
    display_name="序数编码",
    description="类别 → 整数序数映射 (适合有序类别)",
    icon="🔤",
    needs_target=False,
    extra_params=[
        ParamSpec(
            name="mapping",
            type="dict",
            label="自定义映射 {col: {value: code}}",
            default=None,
            advanced=True,
            description='JSON 格式, 例: {"col1": {"a": 1, "b": 2}}',
        ),
    ],
)

CatBoostEncoderNode = _make_encoder_node(
    node_type="catboost_encoder",
    class_path="hscredit.core.encoders",
    class_name="CatBoostEncoder",
    display_name="CatBoost 编码",
    description="带噪声的目标编码 (类似 CatBoost), 适合高基数类别",
    icon="🐱",
    needs_target=True,
    extra_params=[
        ParamSpec(name="sigma", type="float", label="高斯噪声 std", default=None, min=0.0, max=10.0, advanced=True),
        ParamSpec(name="random_state", type="int", label="随机种子", default=None, advanced=True),
    ],
)

OneHotEncoderNode = _make_encoder_node(
    node_type="one_hot_encoder",
    class_path="hscredit.core.encoders",
    class_name="OneHotEncoder",
    display_name="独热编码",
    description="One-Hot 独热编码, 适合低基数类别",
    icon="1️⃣",
    needs_target=False,
    extra_params=[
        ParamSpec(
            name="drop",
            type="select",
            label="是否丢弃第一列 (避共线)",
            default="none",
            choices=[
                {"label": "不丢弃", "value": "none"},
                {"label": "丢弃第一列", "value": "first"},
                {"label": "丢弃最频繁", "value": "if_binary"},
            ],
            advanced=True,
        ),
        ParamSpec(
            name="use_cat_names",
            type="bool",
            label="使用类别名作为列名后缀",
            default=True,
            advanced=True,
        ),
    ],
)


__all__ = [
    "CatBoostEncoderNode",
    "CountEncoderNode",
    "OneHotEncoderNode",
    "OrdinalEncoderNode",
    "TargetEncoderNode",
]