"""Contract 反推 — AST 静态 + 试运行反推 (Phase 6 B36).

依据 docs/node-plugin/01_DESIGN.md 第 1.4 节:

- AST 部分: 推断 input ports (从 ``inputs["xxx"]``)、output ports (从 return dict)、param names (从 kwargs)
- 试运行部分: 用 sample 跑一次, 观察 outputs keys + 启发式 types (DataFrame / Series / 其他 → object)
- 合并: AST 给结构, 试运行给类型验证, 用户最终确认
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InferredContract:
    """反推的 contract."""

    node_type: str = ""
    category: str = "特征工程"
    name: str = ""
    description: str = ""
    icon: str = "🛠️"
    inputs: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    params: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_type": self.node_type,
            "category": self.category,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "params": self.params,
        }


@dataclass
class ContractInferenceResult:
    """完整反推结果."""

    draft_contract: InferredContract
    ast_inferred: dict[str, Any]
    runtime_inferred: dict[str, Any] | None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_contract": self.draft_contract.to_dict(),
            "ast_inferred": self.ast_inferred,
            "runtime_inferred": self.runtime_inferred,
            "warnings": self.warnings,
        }


# ===== AST 反推 =====


def infer_from_ast(code: str) -> dict[str, Any]:
    """AST 静态推断 input/output/param names.

    Returns:
        dict 含:
        - input_ports: 从 ``inputs["xxx"]`` 推断的输入端口名列表
        - output_ports: 从 return dict 推断的输出端口名列表
        - param_names: 从 kwargs 推断的参数名列表
        - class_name: BaseNode 子类名
    """
    tree = ast.parse(code)

    # 找 BaseNode 子类
    basenode_class = None
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        if any(
            (isinstance(b, ast.Name) and b.id == "BaseNode")
            or (isinstance(b, ast.Attribute) and b.attr == "BaseNode")
            for b in cls.bases
        ):
            basenode_class = cls
            break

    if basenode_class is None:
        return {
            "class_name": None,
            "input_ports": [],
            "output_ports": [],
            "param_names": [],
        }

    # 找 run 方法
    run_method = None
    for stmt in basenode_class.body:
        if isinstance(stmt, ast.FunctionDef) and stmt.name == "run":
            run_method = stmt
            break

    if run_method is None:
        return {
            "class_name": basenode_class.name,
            "input_ports": [],
            "output_ports": [],
            "param_names": [],
        }

    # 1. input_ports: 扫描函数体内所有 inputs["xxx"] 形式的下标访问
    input_ports = _extract_dict_subscript_keys(run_method, target_name="inputs")

    # 2. output_ports: 扫描 return 语句的 dict 字面量 keys
    output_ports = _extract_return_dict_keys(run_method)

    # 3. param_names: 扫描 params["xxx"] 形式的下标访问
    param_names = _extract_dict_subscript_keys(run_method, target_name="params")

    # 4. 也支持 kwargs.get("xxx") 形式
    input_ports |= _extract_kwargs_get_keys(run_method, target_name="inputs")
    param_names |= _extract_kwargs_get_keys(run_method, target_name="params")

    return {
        "class_name": basenode_class.name,
        "input_ports": sorted(input_ports),
        "output_ports": sorted(output_ports),
        "param_names": sorted(param_names),
    }


def _extract_dict_subscript_keys(func: ast.FunctionDef, target_name: str) -> set[str]:
    """提取函数体内形如 ``target_name["xxx"]`` 的所有 keys."""
    keys: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Subscript):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == target_name
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
            ):
                keys.add(node.slice.value)
    return keys


def _extract_kwargs_get_keys(func: ast.FunctionDef, target_name: str) -> set[str]:
    """提取函数体内形如 ``target_name.get("xxx")`` / ``target_name.get('xxx', default)`` 的 keys."""
    keys: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == target_name
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                keys.add(node.args[0].value)
    return keys


def _extract_return_dict_keys(func: ast.FunctionDef) -> set[str]:
    """提取 run() 方法内所有 return dict 字面量的 keys."""
    keys: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Return) and node.value is not None:
            _collect_dict_literal_keys(node.value, keys)
    return keys


def _collect_dict_literal_keys(expr: ast.expr, keys: set[str]) -> None:
    """递归收集 dict 字面量 keys (支持嵌套)."""
    if isinstance(expr, ast.Dict):
        for k in expr.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                keys.add(k.value)
    elif isinstance(expr, (ast.List, ast.Tuple)):
        for elt in expr.elts:
            _collect_dict_literal_keys(elt, keys)
    # 其他类型 (Call, Name 等) 跳过 — 静态分析只能看字面量


# ===== 试运行反推 =====


def infer_from_runtime(outputs: dict[str, Any] | None) -> dict[str, Any]:
    """从试运行 outputs 反推 output ports.

    Args:
        outputs: 试运行的 outputs dict, 可能为 None (执行失败)

    Returns:
        dict 含:
        - output_keys: 实际输出 keys 列表
        - output_types: 各 key 的启发式类型 (DataFrame / Series / dict / list / scalar)
    """
    if not outputs:
        return {
            "output_keys": [],
            "output_types": {},
            "status": "no_outputs",
        }

    output_keys = list(outputs.keys())
    output_types = {}
    for key, value in outputs.items():
        output_types[key] = _heuristic_type(value)

    return {
        "output_keys": output_keys,
        "output_types": output_types,
        "status": "success",
    }


def _heuristic_type(value: Any) -> str:
    """启发式类型识别."""
    if value is None:
        return "None"
    # pandas DataFrame / Series
    type_name = type(value).__name__
    if type_name == "DataFrame":
        return "DataFrame"
    if type_name == "Series":
        return "Series"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, list):
        return "list"
    if isinstance(value, str):
        return "str"
    if isinstance(value, (int, float, bool)):
        return type_name
    return f"object ({type_name})"


# ===== 合并 =====


def merge_inference(
    ast_result: dict[str, Any],
    runtime_result: dict[str, Any] | None,
    *,
    node_type: str = "",
    name: str = "",
    category: str = "特征工程",
    icon: str = "🛠️",
) -> ContractInferenceResult:
    """合并 AST + 试运行反推结果 → 最终 draft contract.

    合并策略:
    - inputs/outputs: 优先用 AST 给结构, 试运行给类型; 如果只有其一, 用唯一的
    - params: 用 AST 推断 (param_names)
    - warnings: 类型推断限制说明
    """
    warnings: list[str] = []

    # 1. inputs
    ast_inputs = ast_result.get("input_ports", [])
    inputs = [
        {"name": p, "type": "DataFrame", "required": True, "description": "由 AST 推断"}
        for p in ast_inputs
    ]
    if not ast_inputs:
        warnings.append("无法从 AST 推断输入端口 (代码可能用 *args/**kwargs 或变量访问 inputs)")

    # 2. outputs
    ast_outputs = ast_result.get("output_ports", [])
    runtime_keys = (runtime_result or {}).get("output_keys", [])
    runtime_types = (runtime_result or {}).get("output_types", {})

    # 优先 AST 给结构, 试运行给类型
    output_keys = ast_outputs or runtime_keys
    outputs = []
    for k in output_keys:
        out_type = runtime_types.get(k, "object")
        # 类型推断限制
        if out_type.startswith("object"):
            warnings.append(
                f"输出端口 {k!r} 类型只能反推为 object (无法确定具体 schema, 请人工确认)"
            )
        outputs.append({
            "name": k,
            "type": out_type if out_type != "object" else "object",
            "description": "由 AST + 试运行反推",
        })

    # 3. params
    param_names = ast_result.get("param_names", [])
    params = [
        {"name": p, "type": "Any", "required": False, "default": None, "description": "由 AST 推断"}
        for p in param_names
    ]
    if param_names:
        warnings.append("参数 type 只能反推为 Any, 请手动选择 (str/int/float/bool/select/...)")

    draft = InferredContract(
        node_type=node_type or ast_result.get("class_name", ""),
        category=category,
        name=name or ast_result.get("class_name", ""),
        icon=icon,
        inputs=inputs,
        outputs=outputs,
        params=params,
    )

    return ContractInferenceResult(
        draft_contract=draft,
        ast_inferred={
            "class_name": ast_result.get("class_name"),
            "input_ports_from_inputs": ast_inputs,
            "output_ports_from_return": ast_outputs,
            "param_names_from_kwargs": param_names,
        },
        runtime_inferred=runtime_result,
        warnings=warnings,
    )


__all__ = [
    "ContractInferenceResult",
    "InferredContract",
    "infer_from_ast",
    "infer_from_runtime",
    "merge_inference",
]
