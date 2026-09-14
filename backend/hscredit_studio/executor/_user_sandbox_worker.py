"""User Code Sandbox Worker — 在子进程中执行用户自定义节点 (Phase 6 B36).

依据 docs/node-plugin/01_DESIGN.md 第 4.5 节:

接收 payload (含 code / sample_inputs / sample_params), 在受限子进程内:

1. RestrictedPython 编译用户代码 (AST 黑名单二次校验)
2. exec(code, restricted_globals)
3. 查找 BaseNode 子类
4. 实例化 + 调 run(inputs, sample_params)
5. 把 outputs pickle 到 stdout, 错误 dict 也 pickle

主进程 (_user_sandbox_backend.py) 读 stdout 反序列化.

调用方式:
    python _user_sandbox_worker.py /tmp/payload.pkl

payload 格式 (pickle 序列化):
    {
        "code": str,
        "sample_inputs": dict,  # 通常含 {"df": "<DataFrame parquet bytes>"}
        "sample_params": dict,
        "node_type": str,
    }

输出: stdout 是 pickle 序列化的:
    成功: outputs dict
    失败: {"__sandbox_error__": {...}}
"""

from __future__ import annotations

import io
import os
import pickle
import sys
import traceback
from pathlib import Path


def _setup_path() -> None:
    """把 backend 根目录加入 sys.path.

    worker 位于 backend/hscredit_studio/executor/_user_sandbox_worker.py
    需要回到 backend/ 才能 import hscredit_studio.
    """
    worker_path = Path(__file__).resolve()
    # backend/hscredit_studio/executor/_user_sandbox_worker.py -> backend/
    project_root = worker_path.parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def _serialize_error(exc: BaseException, code: str = "E_UNKNOWN") -> dict:
    """把异常序列化为可 pickle 的 dict."""
    return {
        "__sandbox_error__": {
            "exception_type": type(exc).__name__,
            "code": getattr(exc, "code", code),
            "message": str(exc),
            "details": getattr(exc, "details", {}),
            "traceback": traceback.format_exc()[-2000:],
        }
    }


def _try_pickle_outputs(outputs: dict) -> dict:
    """尝试 pickle outputs, 失败则转为 base64 编码的 dict 占位.

    因为 outputs 可能含 pandas DataFrame / numpy array 等不能 pickle 的对象,
    主进程通过 _save_outputs (services.artifacts) 已经把 DataFrame 转 parquet bytes,
    所以这里应该都是可 pickle 的对象.
    """
    try:
        pickle.dumps(outputs)
        return outputs
    except (pickle.PicklingError, TypeError) as e:
        return _serialize_error(
            e, code="E_OUTPUT_NOT_PICKLABLE"
        )


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: _user_sandbox_worker.py <payload.pkl>\n")
        return 2

    payload_path = sys.argv[1]
    if not os.path.exists(payload_path):
        sys.stderr.write(f"payload file not found: {payload_path}\n")
        return 3

    _setup_path()

    # 抑制 INFO 级日志, 让日志集中到主进程
    import logging
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    # ===== 1. 读 payload =====
    try:
        with open(payload_path, "rb") as f:
            payload = pickle.load(f)
    except Exception as e:
        result = _serialize_error(e, code="E_PAYLOAD_LOAD")
        sys.stdout.buffer.write(pickle.dumps(result))
        return 0

    code = payload.get("code", "")
    sample_inputs = payload.get("sample_inputs", {}) or {}
    sample_params = payload.get("sample_params", {}) or {}
    node_type = payload.get("node_type", "")

    if not code:
        result = _serialize_error(ValueError("code 为空"), code="E_EMPTY_CODE")
        sys.stdout.buffer.write(pickle.dumps(result))
        return 0

    # ===== 2. RestrictedPython 编译 =====
    try:
        from RestrictedPython import compile_restricted
        from RestrictedPython import safe_globals as _rp_safe_globals
        from RestrictedPython.Guards import (
            full_write_guard,
            safe_globals as _guarded_safe_globals,  # 包含 _getattr_/_getitem_ 等守卫
        )
        # 使用 Guards 版本的 safe_globals (包含 _getattr_/_getitem_/_getiter_/safe_open 等)
        restricted_builtins = dict(_guarded_safe_globals)
    except ImportError:
        compile_restricted = None
        _rp_safe_globals = {}
        restricted_builtins = {}

    # 删除危险 builtin
    # __import__ 不在这里 pop: 用户代码 `from x import y` 编译后是 `__import__('x', ...)`,
    # 没了 __import__ 会 ImportError. 改成下面用白名单版本替换它.
    for blocked in ("eval", "exec", "compile", "open", "input", "breakpoint"):
        restricted_builtins.pop(blocked, None)

    # 主动补回 Python class 定义必需的 builtin
    # RestrictedPython 默认 safe_globals 太严, 连 __build_class__ 都没了
    # class 定义需要它, 否则直接 NameError
    import builtins as _bi
    if "__build_class__" not in restricted_builtins and hasattr(_bi, "__build_class__"):
        restricted_builtins["__build_class__"] = _bi.__build_class__

    # 替换 __import__ 为白名单版本: 只允许 import 安全模块
    # 用户的 from hscredit_studio.nodes.base import BaseNode 编译后
    # 就是 __import__('hscredit_studio.nodes.base', ...).
    _ALLOWED_IMPORT_PREFIXES = (
        "hscredit_studio.nodes.base",
        "hscredit_studio.schemas.node_contract",
        "hscredit_studio.schemas",
    )
    # 常用的 stdlib 数据科学白名单 (避免用户 import os/subprocess 等)
    _ALLOWED_IMPORT_STDLIB = frozenset({
        "math", "statistics", "random", "datetime", "json", "re",
        "collections", "itertools", "functools", "typing",
        "pandas", "numpy", "polars",  # 数据栈
    })

    def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        # 同包内相对 import (level > 0) 不放行
        if level != 0:
            raise ImportError("relative import not allowed in sandbox")
        # 白名单检查
        allowed = any(
            name == p or name.startswith(p + ".")
            for p in _ALLOWED_IMPORT_PREFIXES
        ) or name in _ALLOWED_IMPORT_STDLIB
        if not allowed:
            raise ImportError(
                f"import of {name!r} is not allowed in sandbox "
                f"(only {_ALLOWED_IMPORT_STDLIB | set(_ALLOWED_IMPORT_PREFIXES)})"
            )
        return _bi.__import__(name, globals, locals, fromlist, level)

    restricted_builtins["__import__"] = _safe_import

    # RestrictedPython 编译时会注入 _getattr_/_getitem_/_getiter_ 守卫调用,
    # 它们必须在 globals 里 (不是 __builtins__ 里), 否则运行时 NameError.
    # 使用本项目的简化守卫 (见 _restricted_guards.py)
    try:
        from hscredit_studio.executor._restricted_guards import (
            safe_getattr,
            safe_getitem,
            safe_getiter,
            safe_iter_unpack_sequence,
            safe_write,
        )

        restricted_globals_extras = {
            "_getattr_": safe_getattr,
            "_getitem_": safe_getitem,
            "_getiter_": safe_getiter,
            "_iter_unpack_sequence_": safe_iter_unpack_sequence,
            "_write_": safe_write,
        }
    except ImportError:
        restricted_globals_extras = {}

    try:
        if compile_restricted is not None:
            try:
                bytecode = compile_restricted(code, filename="<user_code>", mode="exec")
            except SyntaxError as e:
                result = _serialize_error(e, code="E_SYNTAX_ERROR")
                sys.stdout.buffer.write(pickle.dumps(result))
                return 0
            except Exception as e:
                # RestrictedPython 编译失败 (AST 黑名单触发)
                result = _serialize_error(e, code="E_RESTRICTED_PYTHON")
                sys.stdout.buffer.write(pickle.dumps(result))
                return 0
        else:
            try:
                bytecode = compile(code, filename="<user_code>", mode="exec")
            except SyntaxError as e:
                result = _serialize_error(e, code="E_SYNTAX_ERROR")
                sys.stdout.buffer.write(pickle.dumps(result))
                return 0
    except Exception as e:
        result = _serialize_error(e, code="E_COMPILE")
        sys.stdout.buffer.write(pickle.dumps(result))
        return 0

    # ===== 3. 准备受限命名空间 =====
    # 环境变量已由主进程注入 (SECRET_KEY 等), settings 不会校验失败
    try:
        from hscredit_studio.core.exceptions import HSCreditWorkflowError
        from hscredit_studio.nodes.base import BaseNode
    except ImportError as e:
        result = _serialize_error(e, code="E_IMPORT_BASE")
        sys.stdout.buffer.write(pickle.dumps(result))
        return 0

    # 受限 globals
    restricted_globals = {
        "__builtins__": restricted_builtins if compile_restricted is not None else __builtins__,
        "__name__": "user_module",
        "__metaclass__": type,
        "__doc__": None,
        # 注入业务类 (允许用户直接用, 不需要 import)
        "BaseNode": BaseNode,
        "HSCreditWorkflowError": HSCreditWorkflowError,
        # RestrictedPython 在 Python 3 的 class 定义里需要这些
        "__metaclass__": type,
    }
    # RestrictedPython 编译时要求的守卫函数
    restricted_globals.update(restricted_globals_extras)

    # ===== 4. 执行用户代码 =====
    # 注意: 必须只传 globals, 不传 locals dict. RestrictedPython 编译的 `from x import Y`
    # 会输出 `STORE_NAME Y`, 在 exec(code, globals, locals) 模式下 STORE_NAME 会写到 locals,
    # 而 class body 内的 `LOAD_NAME Y` 只会查 globals (不查 locals) — 名字找不到 → NameError.
    # 不传 locals 时, STORE_NAME 写到 globals (Python 标准行为), LOAD_NAME 就能找到.
    user_globals: dict = {}
    try:
        exec(bytecode, restricted_globals)
        # exec 不传 locals 时, globals 字典会被更新; 我们从中抽出用户定义的类
        user_globals.update({
            k: v for k, v in restricted_globals.items()
            if not k.startswith("_") and k not in {
                "BaseNode", "HSCreditWorkflowError",
            }
        })
    except Exception as e:
        result = _serialize_error(e, code="E_EXEC_USER_CODE")
        sys.stdout.buffer.write(pickle.dumps(result))
        return 0

    # ===== 5. 查找 BaseNode 子类 =====
    basenode_cls = None
    for v in user_globals.values():
        if isinstance(v, type) and issubclass(v, BaseNode) and v is not BaseNode:
            basenode_cls = v
            break

    if basenode_cls is None:
        result = _serialize_error(
            ValueError("未找到继承 BaseNode 的类"),
            code="E_NO_BASENODE_CLASS",
        )
        sys.stdout.buffer.write(pickle.dumps(result))
        return 0

    # ===== 6. 实例化 + 调 run() =====
    try:
        instance = basenode_cls()
        # validate_inputs/validate_params 可选 (BaseNode 默认实现, Stub base 没有)
        for method in ("validate_inputs", "validate_params"):
            fn = getattr(instance, method, None)
            if fn is None:
                continue
            try:
                if method == "validate_inputs":
                    fn(sample_inputs)
                else:
                    fn(sample_params)
            except (NotImplementedError, AttributeError):
                # Stub base 可能没实现, 跳过
                pass
        outputs = instance.run(sample_inputs, sample_params)
    except HSCreditWorkflowError as e:
        result = _serialize_error(e, code=e.code if hasattr(e, "code") else "E_BUSINESS")
        sys.stdout.buffer.write(pickle.dumps(result))
        return 0
    except MemoryError as e:
        result = _serialize_error(e, code="SANDBOX_OOM")
        sys.stdout.buffer.write(pickle.dumps(result))
        return 0
    except Exception as e:
        result = _serialize_error(e, code="E_USER_CODE_EXEC")
        sys.stdout.buffer.write(pickle.dumps(result))
        return 0

    if not isinstance(outputs, dict):
        result = _serialize_error(
            ValueError(f"run() 必须返回 dict, 实际: {type(outputs).__name__}"),
            code="E_RUN_NOT_DICT",
        )
        sys.stdout.buffer.write(pickle.dumps(result))
        return 0

    # ===== 7. 序列化输出 =====
    sys.stdout.buffer.write(pickle.dumps(_try_pickle_outputs(outputs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
