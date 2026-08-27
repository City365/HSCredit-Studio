"""WOE 编码 — 把类别型/分箱后的特征替换为 WOE 值.

复用 ``hscredit.core.encoders.WOEEncoder``。直接对原始类别取值
计算 WOE, 不做数值分箱;若上游已分箱则传入 ``binner`` 作为可选上下文。

注意: WOE 编码监督式, ``fit`` 需要目标列; 当 ``binner`` 输入不为
空时仅记录上下文,不参与 fit/transform。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hscredit_studio.core.exceptions import (
    DependencyError,
    FeatureNotFoundError,
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
class WOEEncoderNode(BaseNode):
    """WOE 编码 — 把类别型特征替换为 WOE 值."""

    contract = NodeContract(
        node_type="woe_encoder",
        category="特征工程",
        name="WOE 编码",
        description="将类别型/分箱后的变量替换为 Weight of Evidence 值",
        icon="🔄",
        inputs=[
            PortSchema(name="df", type="DataFrame", required=True),
            PortSchema(
                name="binner",
                type="BinnerArtifact",
                required=False,
                description="（可选）上游分箱器, 仅记录上下文",
            ),
        ],
        outputs=[
            PortSchema(name="encoder", type="EncoderArtifact", description="训练好的 WOE 编码器"),
            PortSchema(name="woe_df", type="DataFrame", description="WOE 编码后的 DataFrame"),
        ],
        params=[
            ParamSpec(name="features", type="list", label="要编码的特征列表", required=True),
            ParamSpec(name="target", type="str", label="目标列名", required=True),
            ParamSpec(
                name="drop_invariant",
                type="bool",
                label="丢弃常数列",
                default=False,
                advanced=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=300,
        estimated_duration_sec=20,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        try:
            from hscredit.core.encoders import WOEEncoder
        except ImportError as e:
            raise DependencyError(
                f"hscredit.core.encoders.WOEEncoder 不可用: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        df = inputs.get("binned_df")
        if df is None:
            df = inputs.get("df")
        # 多 bin_* 节点汇聚时，df 已被 executor 合并为 list — 合并所有 df 的 *_bin 列
        # (3 个 bin_* 节点各自产一份 df，每份只含本节点分箱列；保留所有 *_bin 列供 WOE)
        if isinstance(df, list):
            if not df:
                df = None
            else:
                merged = df[0]
                for extra in df[1:]:
                    for col in extra.columns:
                        if col not in merged.columns:
                            merged = merged.copy()
                            merged[col] = extra[col]
                df = merged
        if df is None:
            raise ValidationError(
                "缺少必需输入端口 df 或 binned_df",
                details={"node_type": self.contract.node_type, "available_inputs": list(inputs.keys())},
            )
        features = params["features"]
        target = params["target"]
        if not isinstance(features, list) or not features:
            raise ValidationError(
                "features 必须是非空列表",
                details={"node_type": self.contract.node_type, "features": features},
            )
        missing = [f for f in features if f not in df.columns]
        if missing:
            raise FeatureNotFoundError(
                f"以下特征不在数据中: {missing}",
                details={"node_type": self.contract.node_type, "missing_features": missing},
            )
        if target not in df.columns:
            raise ValidationError(
                f"目标列 {target} 不存在",
                details={"node_type": self.contract.node_type, "target": target},
            )

        encoder = WOEEncoder(
            cols=features,
            drop_invariant=bool(params.get("drop_invariant", False)),
            return_df=True,
            target=target,
        )
        try:
            encoder.fit(df[features], df[target])
            woe_features = encoder.transform(df[features])
        except Exception as e:
            raise ValidationError(
                f"WOE 编码失败: {e}",
                details={"node_type": self.contract.node_type, "features": features},
            ) from e
        # WOEEncoder.transform 返回的特征列名与 features 相同（同名列被替换为 WOE 值）。
        # 用 woe_features（已经是 WOE 编码后的 DataFrame）作为 woe_df 主体；
        # 拼上 ``df[target]``（一列）使下游 iv_selector / logistic / score_card 仍能定位目标列。
        # 拼上 ``df.drop(features+[target], axis=1)`` 保留非特征列（如样本 ID、辅助列）。
        keep_cols = [c for c in df.columns if c not in features and c != target]
        woe_df = pd.concat(
            [woe_features.reset_index(drop=True), df[[*keep_cols, target]].reset_index(drop=True)],
            axis=1,
        )
        return {"encoder": encoder, "woe_df": woe_df}
