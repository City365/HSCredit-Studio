"""Sandbox 子进程 worker — 在隔离进程中执行单个节点.

依据 :file:`docs/ROADMAP.md` Phase 3 B14:

> 通过 pickle 协议接收 ``(node_type, inputs, params)``,
> 在子进程中 ``NodeRegistry.get(node_type)().run(inputs, params)``,
> 把 outputs pickle 到 stdout。

调用::

    python _sandbox_worker.py /tmp/payload.pkl

输入文件: pickle 序列化的 ``{"node_type": str, "inputs": dict, "params": dict}``。
输出: stdout 是 pickle 序列化的输出 dict, 或失败时为 ``{"__sandbox_error__": {...}}``。
"""
from __future__ import annotations

import os
import pickle
import sys
import traceback
from pathlib import Path


def _setup_path() -> None:
    """把 backend 根目录加入 sys.path, 确保能 import hscredit_studio."""
    worker_path = Path(__file__).resolve()
    project_root = worker_path.parent.parent  # backend/hscredit_studio/executor/_sandbox_worker.py -> backend
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def _serialize_error(exc: BaseException) -> dict:
    """把异常序列化为可 pickle 的 dict (worker → 主进程错误透传)."""
    return {
        "__sandbox_error__": {
            "exception_type": type(exc).__name__,
            "code": getattr(exc, "code", "E_UNKNOWN"),
            "message": str(exc),
            "details": getattr(exc, "details", {}),
            "traceback": traceback.format_exc()[-2000:],  # 截断尾部 2KB
        }
    }


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: _sandbox_worker.py <payload.pkl>\n")
        return 2

    payload_path = sys.argv[1]
    if not os.path.exists(payload_path):
        sys.stderr.write(f"payload file not found: {payload_path}\n")
        return 3

    _setup_path()

    # 抑制 worker 内的 INFO 级日志 (structlog 默认输出到 stderr), 让日志集中到主进程
    import logging

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    try:
        with open(payload_path, "rb") as f:
            payload = pickle.load(f)
    except Exception as e:
        result = _serialize_error(e)
        sys.stdout.buffer.write(pickle.dumps(result))
        return 0  # 用序列化错误表达, 不让非零退出码触发 subprocess.run 重试逻辑

    node_type = payload.get("node_type")
    inputs = payload.get("inputs", {})
    params = payload.get("params", {})

    try:
        # 延迟 import, 避免 worker 启动阶段就加载重依赖
        from hscredit_studio.core.exceptions import HSCreditWorkflowError
        from hscredit_studio.nodes.registry import NodeRegistry

        node_cls = NodeRegistry.try_get(node_type)
        if node_cls is None:
            raise HSCreditWorkflowError(
                f"节点类型 {node_type} 未注册",
                details={"node_type": node_type},
            )

        node_instance = node_cls()
        node_instance.validate_inputs(inputs)
        node_instance.validate_params(params)
        outputs = node_instance.run(inputs, params)

        if not isinstance(outputs, dict):
            raise HSCreditWorkflowError(
                f"节点 {node_type} run() 必须返回 dict, 实际: {type(outputs).__name__}",
                details={"node_type": node_type},
            )

        sys.stdout.buffer.write(pickle.dumps(outputs))
        return 0

    except HSCreditWorkflowError as e:
        sys.stdout.buffer.write(pickle.dumps(_serialize_error(e)))
        return 0
    except MemoryError as e:
        sys.stdout.buffer.write(
            pickle.dumps(_serialize_error(MemoryError(f"节点 {node_type} OOM: {e}")))
        )
        return 0
    except Exception as e:
        sys.stdout.buffer.write(pickle.dumps(_serialize_error(e)))
        return 0


if __name__ == "__main__":
    sys.exit(main())
