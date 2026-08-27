"""拒绝推断 (Reject Inference) 节点 — 解决贷前样本选择偏差.

业务背景:
贷前模型只用"已放款且表现已知"的样本训练, 但实际预测时要对"申请客户"评分。
放款决策本身可能拒绝了一些客户, 形成了样本选择偏差。
拒绝推断通过历史"已知拒绝"客户回溯估算其坏率, 扩充训练样本,
提高评分卡在真实客群上的区分度。

实现方法 (Phase 2 - 简化版):
- ``hard_cutoff``: 对拒绝客户按模型分桶, 用已放款客户的坏率分布作为先验,
  加权推断拒绝客户的预期坏率
- ``fuzzy_augmentation``: 将拒绝客户按评分相似度匹配到已放款客户,
  按相似度加权采样扩充训练集
"""
from __future__ import annotations

from typing import Any

import numpy as np
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
    ParamChoice,
    ParamSpec,
    PortSchema,
)


@register_node
class RejectInferenceNode(BaseNode):
    """拒绝推断 (扩充训练样本, 缓解样本选择偏差)."""

    contract = NodeContract(
        node_type="reject_inference",
        category="数据接入",
        name="拒绝推断",
        description="用 hard_cutoff 或 fuzzy_augmentation 方法, 从拒绝客户推断坏率, 扩充训练集",
        icon="🚦",
        inputs=[
            PortSchema(name="df", type="DataFrame", required=True, description="已放款客户数据"),
            PortSchema(name="rejected_df", type="DataFrame", required=True, description="已拒绝客户数据"),
            PortSchema(name="score", type="DataFrame", required=False, aliases=["df_score"], description="(可选) 已放款客户的模型评分"),
        ],
        outputs=[
            PortSchema(name="inferred_df", type="DataFrame", description="扩充后的训练集 (含推断拒绝客户)"),
            PortSchema(name="inference_stats", type="JSON", description="推断统计 (各分箱推断坏率)"),
        ],
        params=[
            ParamSpec(name="target", type="str", label="目标列名", required=True),
            ParamSpec(
                name="method",
                type="str",
                label="推断方法",
                default="fuzzy_augmentation",
                choices=[
                    ParamChoice(label="硬截止 (hard_cutoff)", value="hard_cutoff"),
                    ParamChoice(label="模糊增强 (fuzzy_augmentation)", value="fuzzy_augmentation"),
                ],
            ),
            ParamSpec(
                name="score_column",
                type="str",
                label="分数列名 (硬截止法必需)",
                default="",
                advanced=True,
            ),
            ParamSpec(
                name="cutoff_threshold",
                type="float",
                label="拒绝阈值 (硬截止法)",
                default=0.5,
                min=0.0,
                max=1.0,
                advanced=True,
            ),
            ParamSpec(
                name="n_bins",
                type="int",
                label="分箱数",
                default=10,
                min=3,
                max=50,
                advanced=True,
            ),
            ParamSpec(
                name="augmentation_ratio",
                type="float",
                label="扩充比例 (拒绝客户采样倍数)",
                default=1.0,
                min=0.1,
                max=10.0,
                advanced=True,
            ),
        ],
        cache=CacheConfig(),
        timeout_sec=120,
        estimated_duration_sec=15,
    )

    def run(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        df = inputs["df"]
        rejected_df = inputs["rejected_df"]
        target = params["target"]
        method = params.get("method", "fuzzy_augmentation")
        n_bins = int(params.get("n_bins", 10))
        aug_ratio = float(params.get("augmentation_ratio", 1.0))

        if target not in df.columns:
            raise FeatureNotFoundError(
                f"目标列 {target} 不在已放款数据中",
                details={"node_type": self.contract.node_type, "target": target},
            )
        if target not in rejected_df.columns:
            raise ValidationError(
                f"目标列 {target} 不在拒绝数据中 (拒绝数据必须含推断目标)",
                details={"node_type": self.contract.node_type},
            )

        if method == "hard_cutoff":
            return self._hard_cutoff(df, rejected_df, target, params)
        elif method == "fuzzy_augmentation":
            return self._fuzzy_augmentation(df, rejected_df, target, n_bins, aug_ratio)
        else:
            raise ValidationError(
                f"未知推断方法: {method}",
                details={"node_type": self.contract.node_type},
            )

    def _hard_cutoff(
        self,
        df: pd.DataFrame,
        rejected_df: pd.DataFrame,
        target: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """硬截止法: 已放款客户分箱 → 用每箱坏率推断拒绝客户标签."""
        score_col = params.get("score_column")
        threshold = float(params.get("cutoff_threshold", 0.5))
        n_bins = int(params.get("n_bins", 10))

        if not score_col:
            raise ValidationError(
                "硬截止法需要 score_column 参数",
                details={"node_type": self.contract.node_type},
            )
        if score_col not in df.columns:
            raise FeatureNotFoundError(
                f"分数列 {score_col} 不在已放款数据中",
                details={"node_type": self.contract.node_type, "missing": score_col},
            )
        if score_col not in rejected_df.columns:
            raise FeatureNotFoundError(
                f"分数列 {score_col} 不在拒绝数据中",
                details={"node_type": self.contract.node_type, "missing": score_col},
            )

        # 已放款客户按分数分箱
        df_binned = df.copy()
        df_binned["_bin"] = pd.qcut(df_binned[score_col], q=n_bins, labels=False, duplicates="drop")
        bin_stats = df_binned.groupby("_bin").agg(
            bad_rate=(target, "mean"),
            n=("_bin", "size"),
        ).reset_index()

        # 拒绝客户按同一分箱边界推断坏率
        rej_binned = rejected_df.copy()
        rej_binned["_bin"] = pd.qcut(rej_binned[score_col], q=n_bins, labels=False, duplicates="drop")
        # 映射坏率
        bin_badrate = dict(zip(bin_stats["_bin"], bin_stats["bad_rate"]))
        rej_binned["_inferred_target"] = rej_binned["_bin"].map(
            lambda b: bin_badrate.get(int(b), df[target].mean())
        )
        # 二值化 (按阈值)
        rej_binned[target] = (rej_binned["_inferred_target"] >= threshold).astype(int)

        # 合并
        augmented = pd.concat(
            [df, rej_binned.drop(columns=["_bin", "_inferred_target"])],
            ignore_index=True,
        )
        stats = {
            "method": "hard_cutoff",
            "n_accepted": len(df),
            "n_rejected_inferred": len(rej_binned),
            "n_total": len(augmented),
            "bin_stats": bin_stats.to_dict(orient="records"),
            "overall_accepted_bad_rate": float(df[target].mean()),
            "overall_rejected_inferred_bad_rate": float(rej_binned[target].mean()),
        }
        return {"inferred_df": augmented, "inference_stats": stats}

    def _fuzzy_augmentation(
        self,
        df: pd.DataFrame,
        rejected_df: pd.DataFrame,
        target: str,
        n_bins: int,
        aug_ratio: float,
    ) -> dict[str, Any]:
        """模糊增强: 拒绝客户按特征相似度匹配到已放款客户, 采样扩充."""
        # 选数值特征用于相似度
        numeric_cols = [
            c for c in df.columns
            if c != target
            and pd.api.types.is_numeric_dtype(df[c])
            and pd.api.types.is_numeric_dtype(rejected_df[c])
        ]
        if not numeric_cols:
            raise ValidationError(
                "数据中没有可用的数值特征用于相似度匹配",
                details={"node_type": self.contract.node_type},
            )

        # 分箱 (qcut) 把数值特征离散化, 用于相似度匹配
        accepted_binned = df.copy()
        rejected_binned = rejected_df.copy()
        bin_edges: dict[str, np.ndarray] = {}
        for col in numeric_cols:
            try:
                _, edges = pd.qcut(df[col], q=n_bins, retbins=True, duplicates="drop")
                accepted_binned[col] = pd.cut(df[col], bins=edges, labels=False, include_lowest=True)
                rejected_binned[col] = pd.cut(rejected_df[col], bins=edges, labels=False, include_lowest=True)
                bin_edges[col] = edges
            except Exception:
                # 单值列: 跳过
                accepted_binned[col] = 0
                rejected_binned[col] = 0

        # 按分箱键分组匹配
        accepted_binned["_fingerprint"] = accepted_binned[numeric_cols].apply(
            lambda r: tuple(r), axis=1
        )
        rejected_binned["_fingerprint"] = rejected_binned[numeric_cols].apply(
            lambda r: tuple(r), axis=1
        )

        accepted_groups = {
            fp: group[target].values for fp, group in accepted_binned.groupby("_fingerprint")
        }
        global_bad_rate = float(df[target].mean())

        # 给每个拒绝客户分配推断标签 (从匹配组随机采样)
        rng = np.random.default_rng(seed=42)
        inferred_targets: list[int] = []
        match_counts: list[int] = []
        for fp in rejected_binned["_fingerprint"]:
            candidates = accepted_groups.get(fp)
            if candidates is not None and len(candidates) > 0:
                # 采样一个
                inferred_targets.append(int(rng.choice(candidates)))
                match_counts.append(len(candidates))
            else:
                # 没匹配上, 用全局坏率 + 伯努利采样
                inferred_targets.append(int(rng.binomial(1, global_bad_rate)))
                match_counts.append(0)

        rejected_binned[target] = inferred_targets
        match_series = pd.Series(match_counts)

        # 按 aug_ratio 采样拒绝客户 (默认全部)
        n_sample = min(len(rejected_binned), int(len(rejected_binned) * aug_ratio))
        sampled_rejected = rejected_binned.sample(n=n_sample, random_state=42)

        # 合并
        augmented = pd.concat([df, sampled_rejected], ignore_index=True)
        stats = {
            "method": "fuzzy_augmentation",
            "n_accepted": len(df),
            "n_rejected_inferred": n_sample,
            "n_total": len(augmented),
            "n_features_used": len(numeric_cols),
            "match_rate": float((match_series > 0).mean()),
            "global_bad_rate": global_bad_rate,
            "inferred_bad_rate": float(np.mean(inferred_targets)),
        }
        return {"inferred_df": augmented, "inference_stats": stats}