"""模型训练节点族 — 新增 4 个模型 (Phase 6 B36).

封装 hscredit 的 4 个新模型:

- ``lightgbm`` — LightGBM 梯度提升
- ``catboost`` — CatBoost 梯度提升 (类别特征友好)
- ``ngboost`` — NGBoost 自然梯度提升 (概率预测 + 不确定性)
- ``random_forest`` — sklearn 随机森林

每个节点都遵循与 XGBoost 一致的模式:

- 输入 ``df`` (DataFrame)
- 参数 ``target`` (workflow_scoped) + ``features`` (列表)
- 输出 ``model`` + ``metrics`` (AUC/KS/Gini) + ``importance`` (特征重要性)

依赖按需 import, 未安装对应包时给出 DependencyError, 不阻塞其它节点.
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
from hscredit_studio.nodes._common import target_param
from hscredit_studio.schemas.node_contract import (
    CacheConfig,
    NodeContract,
    ParamChoice,
    ParamSpec,
    PortSchema,
)


# ===== 共享 run() 模板 =====


def _validate_inputs_and_split(self, params):
    """通用训练前置: 拿 df/features/target, 切 train/val (8:2)."""
    df = resolve_dataframe_input(
        inputs=None,  # placeholder, 由 caller 传入
        node_type=self.contract.node_type,
        aliases=("df", "woe_df", "selected_df", "binned_df", "encoded_df"),
    )
    # ↑ 调用方覆盖: 见 run() 实现里把 inputs 传进来
    raise NotImplementedError  # actual logic inlined below


def _generic_model_run(model_factory, model_kwargs_keys, package_name, supports_eval_set=True):
    """生成 run() 闭包.

    Args:
        model_factory: (model_kwargs) -> 已构造模型实例
        model_kwargs_keys: 从 params 中提取哪些 key 传给模型
        package_name: 友好提示 ("lightgbm"/"catboost"/...)
        supports_eval_set: 是否支持早停 (LightGBM/CatBoost/XGBoost 支持, RandomForest 不支持)
    """
    def run(self, inputs, params):
        df = resolve_dataframe_input(
            inputs,
            self.contract.node_type,
            aliases=("df", "woe_df", "selected_df", "binned_df", "encoded_df"),
        )
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
        features = coerce_features_param(params.get("features"), list(df.columns), self.contract.node_type)
        X = df[features].values
        y = df[target].values

        model_kwargs = {k: params[k] for k in model_kwargs_keys if k in params}
        try:
            model = model_factory(model_kwargs)
        except ImportError as e:
            raise DependencyError(
                f"{package_name} 未安装, 请安装后重试: {e}",
                details={"node_type": self.contract.node_type, "package": package_name},
            ) from e
        except Exception as e:
            raise ValidationError(
                f"构造 {package_name} 模型失败: {e}",
                details={"node_type": self.contract.node_type},
            ) from e

        try:
            if supports_eval_set:
                from sklearn.model_selection import train_test_split

                X_tr, X_va, y_tr, y_va = train_test_split(
                    X, y, test_size=0.2, random_state=42, stratify=y if len(set(y)) > 1 else None
                )
                try:
                    model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
                except TypeError:
                    # fallback: 不支持 eval_set
                    model.fit(X_tr, y_tr)
            else:
                model.fit(X, y)
        except Exception as e:
            raise DependencyError(
                f"{package_name} 训练失败: {e}",
                details={"node_type": self.contract.node_type, "package": package_name},
            ) from e

        metrics: dict[str, Any] = {}
        try:
            from sklearn.metrics import roc_auc_score
            from hscredit.core.metrics import ks as ks_func

            y_proba = model.predict_proba(X)[:, 1]
            metrics["auc"] = float(roc_auc_score(y, y_proba))
            metrics["ks"] = float(ks_func(y, y_proba))
            metrics["gini"] = 2 * metrics["auc"] - 1
        except Exception as e:
            metrics["warning"] = f"指标计算失败: {e}"

        importance = _extract_importance(model, features)
        return {"model": model, "metrics": metrics, "importance": importance}

    return run


def _extract_importance(model: Any, features: list[str]) -> pd.DataFrame:
    """统一提取特征重要性: 支持 model.feature_importances_ 与 get_feature_importance()."""
    try:
        if hasattr(model, "get_feature_importance"):
            imp = model.get_feature_importance()
            if isinstance(imp, dict):
                df = pd.DataFrame(imp)
                df["feature"] = features[: len(df)]
                if "gain" in df.columns:
                    df = df.sort_values("gain", ascending=False).reset_index(drop=True)
                return df
        if hasattr(model, "feature_importances_"):
            df = pd.DataFrame(
                {
                    "feature": features,
                    "gain": list(model.feature_importances_),
                }
            )
            return df.sort_values("gain", ascending=False).reset_index(drop=True)
    except Exception:
        pass
    return pd.DataFrame({"feature": features, "gain": [0.0] * len(features)})


def _make_model_node(
    node_type: str,
    display_name: str,
    description: str,
    icon: str,
    package_name: str,
    extra_params: list[ParamSpec] | None = None,
    model_import_path: str | None = None,
    class_name: str | None = None,
    param_filter: list[str] | None = None,
    supports_eval_set: bool = True,
):
    """生成模型训练节点."""
    params: list[ParamSpec] = [
        target_param(),
        ParamSpec(name="features", type="list", label="特征列表", required=True),
        ParamSpec(name="n_estimators", type="int", label="树/轮数", default=300, min=10, max=5000),
        ParamSpec(name="learning_rate", type="float", label="学习率", default=0.1, min=0.001, max=1.0),
        ParamSpec(name="random_state", type="int", label="随机种子", default=42, advanced=True),
    ]
    if extra_params:
        params.extend(extra_params)

    node_contract = NodeContract(
        node_type=node_type,
        category="模型训练",
        name=display_name,
        description=description,
        icon=icon,
        inputs=[
            PortSchema(
                name="df",
                type="DataFrame",
                required=True,
                aliases=["woe_df", "selected_df", "binned_df", "encoded_df"],
            )
        ],
        outputs=[
            PortSchema(name="model", type="ModelArtifact", description="训练好的模型"),
            PortSchema(name="metrics", type="JSON", description="训练集评估指标 (AUC/KS/Gini)"),
            PortSchema(name="importance", type="DataFrame", description="特征重要性"),
        ],
        params=params,
        cache=CacheConfig(),
        timeout_sec=900,
        estimated_duration_sec=60,
        tags=["model_training"],
        version="1.0.0",
    )

    import_path = model_import_path or f"hscredit.core.models"
    cls_name = class_name or display_name.replace(" ", "")

    def _factory(model_kwargs: dict[str, Any]) -> Any:
        import importlib

        # 兼容 `from hscredit.core.models import LightGBM` 与 `from hscredit.core.models.boosting import LightGBM`
        for path in [import_path, import_path + ".boosting", import_path + ".classical"]:
            try:
                mod = importlib.import_module(path)
                cls = getattr(mod, cls_name, None)
                if cls is not None:
                    return cls(**model_kwargs)
            except ImportError:
                continue
        raise DependencyError(
            f"无法找到 {cls_name}, 检查 hscredit 安装",
            details={"node_type": node_type, "class": cls_name},
        )

    param_keys = param_filter or ["n_estimators", "learning_rate", "random_state"]

    @register_node
    class _GeneratedNode(BaseNode):
        contract = node_contract

    setattr(
        _GeneratedNode,
        "run",
        _generic_model_run(_factory, param_keys, package_name, supports_eval_set),
    )
    _GeneratedNode.__name__ = f"{node_type.title().replace('_', '')}Node"
    return _GeneratedNode


# ===== 4 个新模型节点 =====

LightGBMNode = _make_model_node(
    node_type="lightgbm",
    display_name="LightGBM",
    description="LightGBM 梯度提升树 (二分类), 自动早停",
    icon="🌲",
    package_name="lightgbm",
    class_name="LightGBM",
    param_filter=["n_estimators", "learning_rate", "random_state"],
    extra_params=[
        ParamSpec(name="num_leaves", type="int", label="叶子数", default=31, min=2, max=512, advanced=True),
        ParamSpec(name="max_depth", type="int", label="最大深度 (-1=不限)", default=-1, min=-1, max=32, advanced=True),
        ParamSpec(name="subsample", type="float", label="样本采样", default=1.0, min=0.1, max=1.0, advanced=True),
        ParamSpec(name="colsample_bytree", type="float", label="特征采样", default=1.0, min=0.1, max=1.0, advanced=True),
        ParamSpec(name="reg_alpha", type="float", label="L1 正则", default=0.0, advanced=True),
        ParamSpec(name="reg_lambda", type="float", label="L2 正则", default=0.0, advanced=True),
        ParamSpec(name="min_child_samples", type="int", label="叶子最小样本数", default=20, min=1, advanced=True),
    ],
)

CatBoostNode = _make_model_node(
    node_type="catboost",
    display_name="CatBoost",
    description="CatBoost 梯度提升 (类别特征自动处理), 自动早停",
    icon="🐱",
    package_name="catboost",
    class_name="CatBoost",
    param_filter=["n_estimators", "learning_rate", "random_state"],
    extra_params=[
        ParamSpec(name="depth", type="int", label="树深度", default=6, min=2, max=16, advanced=True),
        ParamSpec(name="l2_leaf_reg", type="float", label="L2 正则", default=3.0, advanced=True),
        ParamSpec(name="subsample", type="float", label="样本采样", default=1.0, advanced=True),
    ],
)

NGBoostNode = _make_model_node(
    node_type="ngboost",
    display_name="NGBoost",
    description="NGBoost 自然梯度提升, 输出概率 + 不确定性",
    icon="📐",
    package_name="ngboost",
    class_name="NGBoost",
    param_filter=["n_estimators", "learning_rate", "random_state"],
    extra_params=[
        ParamSpec(name="base_max_depth", type="int", label="基学习器深度", default=3, min=2, max=10, advanced=True),
        ParamSpec(name="col_sample", type="float", label="特征采样", default=1.0, min=0.1, max=1.0, advanced=True),
    ],
)

RandomForestNode = _make_model_node(
    node_type="random_forest",
    display_name="Random Forest",
    description="sklearn 随机森林, 简单稳健",
    icon="🌳",
    package_name="sklearn",
    model_import_path="hscredit.core.models.classical",
    class_name="RandomForest",
    param_filter=["n_estimators", "random_state"],
    supports_eval_set=False,
    extra_params=[
        ParamSpec(name="max_depth", type="int", label="最大深度 (None=不限)", default=None, min=2, max=32, advanced=True),
        ParamSpec(name="min_samples_split", type="int", label="节点分裂最小样本", default=2, min=2, advanced=True),
        ParamSpec(name="min_samples_leaf", type="int", label="叶子最小样本", default=1, min=1, advanced=True),
        ParamSpec(
            name="max_features",
            type="select",
            label="最大特征数",
            default="sqrt",
            choices=[
                ParamChoice(label="sqrt", value="sqrt"),
                ParamChoice(label="log2", value="log2"),
                ParamChoice(label="None (全部)", value=None),
            ],
            advanced=True,
        ),
        ParamSpec(
            name="class_weight",
            type="select",
            label="类别权重",
            default=None,
            choices=[
                ParamChoice(label="None", value=None),
                ParamChoice(label="balanced", value="balanced"),
                ParamChoice(label="balanced_subsample", value="balanced_subsample"),
            ],
            advanced=True,
        ),
    ],
)


__all__ = [
    "CatBoostNode",
    "LightGBMNode",
    "NGBoostNode",
    "RandomForestNode",
]