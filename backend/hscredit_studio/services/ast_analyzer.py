"""AST 静态分析器 — 校验用户代码 (Phase 6 B36).

依据 docs/node-plugin/01_DESIGN.md 第 3.4 节:

校验规则:
1. 必须有 BaseNode 子类
2. 必须有 contract 类变量
3. 必须有 run(self, inputs, params) 方法
4. run 必须返回 dict
5. 黑名单 import (os/subprocess/socket/ctypes/pickle/...)
6. 黑名单 builtin 调用 (eval/exec/__import__/open)
7. 黑名单 dunder 属性访问

使用 :mod:`ast` 标准库, 零额外依赖 (RestrictedPython 作为第二道防线).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any


# ===== 黑/白名单 =====

# 禁止导入的模块
BLOCKED_IMPORTS = frozenset({
    "os", "sys", "subprocess", "socket", "shutil", "ctypes",
    "pickle", "marshal", "shelve", "importlib",
    "code", "codeop", "pty", "fcntl", "resource",
    "multiprocessing", "threading", "asyncio",
    "urllib", "urllib2", "urllib3", "httplib",
    "requests", "http", "webbrowser",
    "smtplib", "poplib", "imaplib", "ftplib", "telnetlib",
    "ssl", "socket",
})

# 允许的 builtin (黑名单模式: 不在白名单的禁止)
BLOCKED_BUILTINS = frozenset({
    "eval", "exec", "compile", "__import__",
    "open", "input", "breakpoint",
    "globals", "locals",  # 允许 getattr 等, 但禁止全局变量访问
    "delattr",  # 通常不需要
})

# 禁止的属性名 (dunder 排除白名单)
ALLOWED_DUNDERS = frozenset({
    "__init__", "__str__", "__repr__", "__name__",
    "__class__", "__dict__", "__doc__",
})


# ===== 数据结构 =====


@dataclass
class ValidationIssue:
    """单个校验问题."""

    line: int
    column: int = 0
    severity: str = "error"  # 'error' / 'warning'
    rule: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "rule": self.rule,
            "message": self.message,
        }


@dataclass
class ASTPreview:
    """AST 解析后的代码结构预览."""

    class_name: str | None = None
    has_contract: bool = False
    contract_node: ast.expr | None = None
    has_run_method: bool = False
    run_signature: dict[str, Any] | None = None
    imports: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    base_classes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_name": self.class_name,
            "has_contract": self.has_contract,
            "has_run_method": self.has_run_method,
            "run_signature": self.run_signature,
            "imports": self.imports,
            "methods": self.methods,
            "base_classes": self.base_classes,
        }


@dataclass
class ValidationResult:
    """完整校验结果."""

    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    ast_preview: ASTPreview | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "issues": [i.to_dict() for i in self.issues],
            "ast_preview": self.ast_preview.to_dict() if self.ast_preview else None,
        }


# ===== 主入口 =====


def parse_user_code(code: str) -> ast.Module:
    """解析用户代码 → AST, 失败抛 ValueError."""
    try:
        return ast.parse(code, filename="<user_code>")
    except SyntaxError as e:
        raise ValueError(f"语法错误 (line {e.lineno}, col {e.offset}): {e.msg}") from e


def validate_user_code(code: str) -> ValidationResult:
    """完整校验用户代码 (语法 + AST 静态分析).

    Returns:
        ValidationResult 含 valid/issues/ast_preview
    """
    issues: list[ValidationIssue] = []

    # 1. 语法解析
    try:
        tree = parse_user_code(code)
    except ValueError as e:
        issues.append(ValidationIssue(
            line=0, column=0, severity="error",
            rule="syntax_error", message=str(e),
        ))
        return ValidationResult(valid=False, issues=issues)

    # 2. AST 静态分析
    issues.extend(_check_imports(tree))
    issues.extend(_check_builtins(tree))
    issues.extend(_check_dunder_access(tree))
    issues.extend(_check_base_structure(tree))

    # 3. AST 预览
    ast_preview = _extract_preview(tree)

    # 4. 综合判断
    valid = not any(i.severity == "error" for i in issues)
    return ValidationResult(valid=valid, issues=issues, ast_preview=ast_preview)


# ===== 子检查 =====


def _check_imports(tree: ast.Module) -> list[ValidationIssue]:
    """扫描所有 import 语句, 拦截黑名单模块."""
    issues: list[ValidationIssue] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in BLOCKED_IMPORTS:
                    issues.append(ValidationIssue(
                        line=node.lineno, column=node.col_offset,
                        severity="error",
                        rule="import_blocked",
                        message=f"禁止导入 {alias.name!r} 模块",
                    ))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top = module.split(".")[0]
            if top in BLOCKED_IMPORTS:
                issues.append(ValidationIssue(
                    line=node.lineno, column=node.col_offset,
                    severity="error",
                    rule="import_blocked",
                    message=f"禁止从 {module!r} 导入 (from ... import ...)",
                ))
    return issues


def _check_builtins(tree: ast.Module) -> list[ValidationIssue]:
    """扫描 eval/exec/compile/__import__/open 调用."""
    issues: list[ValidationIssue] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _resolve_call_name(node.func)
            if func_name in BLOCKED_BUILTINS:
                issues.append(ValidationIssue(
                    line=node.lineno, column=node.col_offset,
                    severity="error",
                    rule="builtin_blocked",
                    message=f"禁止使用 {func_name!r} 函数",
                ))
    return issues


def _resolve_call_name(func: ast.expr) -> str | None:
    """解析 Call.func 的名字字符串 (如 eval, os.system)."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        # 如 os.system → 返回 'system' (只取末段)
        return func.attr
    return None


def _check_dunder_access(tree: ast.Module) -> list[ValidationIssue]:
    """扫描 __xxx__ 属性访问 (除白名单)."""
    issues: list[ValidationIssue] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                if node.attr not in ALLOWED_DUNDERS:
                    issues.append(ValidationIssue(
                        line=node.lineno, column=node.col_offset,
                        severity="error",
                        rule="dunder_blocked",
                        message=f"禁止访问 dunder 属性 {node.attr!r}",
                    ))
    return issues


def _check_base_structure(tree: ast.Module) -> list[ValidationIssue]:
    """检查类继承 / contract / run 方法存在性."""
    issues: list[ValidationIssue] = []
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

    # 必须有 BaseNode 子类
    basenode_class = None
    for cls in classes:
        if _is_basenode_subclass(cls):
            basenode_class = cls
            break
    if basenode_class is None:
        issues.append(ValidationIssue(
            line=1, column=0, severity="error",
            rule="must_inherit_basemethod",
            message=f"代码必须定义一个继承 BaseNode 的类 (发现 {len(classes)} 个类)",
        ))
        return issues

    # 必须有 contract = NodeContract(...) 类变量
    has_contract = False
    for stmt in basenode_class.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == "contract":
                    has_contract = True
                    break
    if not has_contract:
        issues.append(ValidationIssue(
            line=basenode_class.lineno, column=0, severity="error",
            rule="missing_contract",
            message=f"类 {basenode_class.name} 必须定义 contract = NodeContract(...) 类变量",
        ))

    # 必须有 run 方法
    run_method = None
    for stmt in basenode_class.body:
        if isinstance(stmt, ast.FunctionDef) and stmt.name == "run":
            run_method = stmt
            break
    if run_method is None:
        issues.append(ValidationIssue(
            line=basenode_class.lineno, column=0, severity="error",
            rule="missing_run_method",
            message=f"类 {basenode_class.name} 必须实现 run() 方法",
        ))
    else:
        # 检查 run 签名: (self, inputs, params) 或 (self, inputs: dict, params: dict)
        if len(run_method.args.args) < 3:
            issues.append(ValidationIssue(
                line=run_method.lineno, column=run_method.col_offset,
                severity="error",
                rule="invalid_run_signature",
                message=f"run() 必须接受 (self, inputs, params) 三个参数",
            ))

    return issues


def _is_basenode_subclass(cls: ast.ClassDef) -> bool:
    """检查类是否继承 BaseNode (含间接继承 BaseNode 的)."""
    for base in cls.bases:
        if isinstance(base, ast.Name) and base.id == "BaseNode":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "BaseNode":
            return True
    return False


def _extract_preview(tree: ast.Module) -> ASTPreview:
    """提取代码结构预览 (类名 / import / 方法等)."""
    preview = ASTPreview()

    # imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                preview.imports.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            names = ", ".join(a.name for a in node.names)
            preview.imports.append(f"from {node.module} import {names}")

    # 类
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        if not _is_basenode_subclass(cls):
            continue
        preview.class_name = cls.name
        preview.base_classes = [ast.unparse(b) for b in cls.bases]
        for stmt in cls.body:
            if isinstance(stmt, ast.FunctionDef):
                preview.methods.append(stmt.name)
                if stmt.name == "run":
                    preview.has_run_method = True
                    preview.run_signature = {
                        "args": [
                            {"name": a.arg, "annotation": ast.unparse(a.annotation) if a.annotation else None}
                            for a in stmt.args.args
                        ],
                        "returns": ast.unparse(stmt.returns) if stmt.returns else None,
                    }
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id == "contract":
                        preview.has_contract = True

    return preview


__all__ = [
    "ALLOWED_DUNDERS",
    "ASTPreview",
    "BLOCKED_BUILTINS",
    "BLOCKED_IMPORTS",
    "ValidationIssue",
    "ValidationResult",
    "parse_user_code",
    "validate_user_code",
]
