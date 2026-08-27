"""节点沙箱执行 — Phase 3 B14.

依据 :file:`docs/ROADMAP.md` Phase 3 B14:

> 把节点执行从进程内 Python 迁到隔离沙箱 (K8s Job / Docker), 默认 ``subprocess`` 后端。
> 资源配额: 默认 ``4Gi / 2 CPU / 300s timeout``。
> 主进程负责 DB / Redis / Celery 协调, 子进程负责纯 ``node.run(inputs, params)``。

架构:

::

    [主进程: tasks.py]                              [子进程: _sandbox_worker.py]
    ┌────────────────────┐                         ┌─────────────────────────────┐
    │ 1. 加载 inputs      │   pickle.dumps          │ 4. pickle.loads             │
    │ 2. 缓存检查          │ ─────────────────────▶  │ 5. node_instance.run()     │
    │ 3. sandbox.run_node │   pickle.dumps          │ 6. pickle.dumps            │
    │ 7. 落盘产物         │ ◀─────────────────────  │                             │
    └────────────────────┘                         └─────────────────────────────┘

抽象 :class:`SandboxBackend`, 三种实现:

- :class:`SubprocessSandbox` — 默认, 子进程 + timeout, 跨平台
- :class:`InProcessSandbox` — 回退 (SANDBOX_ENABLED=False), 用于单测与早期 dev
- :class:`DockerSandbox` — 占位, 待 B14 后续迭代实现

错误约定:

- :class:`SandboxTimeoutError` → NodeExecution status='failed', code='SANDBOX_TIMEOUT'
- :class:`SandboxOOMError` → NodeExecution status='failed', code='SANDBOX_OOM'
- 其他 :class:`SandboxError` → 透传原异常信息
"""
from __future__ import annotations

import abc
import contextlib
import os
import pickle
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from hscredit_studio.core.config import settings
from hscredit_studio.core.logging import get_logger

_log = get_logger(__name__)


# ===== 错误类型 =====


class SandboxError(Exception):
    """沙箱执行通用错误."""


class SandboxTimeoutError(SandboxError):
    """沙箱执行超时 (B14 验收: 死循环节点 300s 后被终止)."""


class SandboxOOMError(SandboxError):
    """沙箱内存超限 (subprocess 后端在 Windows 上无法直接检测, 仅在 Linux 上生效)."""


class SandboxBackend(abc.ABC):
    """沙箱后端抽象."""

    @abc.abstractmethod
    async def execute(self, node_type: str, inputs: dict, params: dict) -> dict:
        """在沙箱内执行节点.

        Args:
            node_type: 节点类型标识 (e.g. ``csv_ingest``).
            inputs: 节点输入字典 (含 DataFrame 等大对象, 由后端负责序列化).
            params: 节点参数字典.

        Returns:
            节点输出字典.

        Raises:
            SandboxTimeoutError: 节点执行超时.
            SandboxOOMError: 节点内存超限.
            SandboxError: 其他沙箱执行错误.
        """
        raise NotImplementedError


class InProcessSandbox(SandboxBackend):
    """进程内执行 (SANDBOX_ENABLED=False 时使用, 用于单测与早期 dev)."""

    async def execute(self, node_type: str, inputs: dict, params: dict) -> dict:
        from hscredit_studio.nodes.registry import NodeRegistry

        node_cls = NodeRegistry.try_get(node_type)
        if node_cls is None:
            raise SandboxError(f"节点类型未注册: {node_type}")
        node_instance = node_cls()
        node_instance.validate_inputs(inputs)
        node_instance.validate_params(params)
        return node_instance.run(inputs, params)


class SubprocessSandbox(SandboxBackend):
    """子进程沙箱 (默认后端).

    通过 pickle 序列化 inputs/outputs, 子进程执行 ``node.run``。
    资源限制: 仅 timeout (跨平台); Linux 上额外支持 RLIMIT_AS。
    """

    WORKER_RELATIVE_PATH = "hscredit_studio/executor/_sandbox_worker.py"

    def __init__(self, timeout_sec: int | None = None) -> None:
        self.timeout_sec = timeout_sec or settings.sandbox_timeout_sec
        self._project_root = self._find_project_root()

    def _find_project_root(self) -> Path:
        """定位 backend 项目根目录 (含 hscredit_studio 包)."""
        current = Path(__file__).resolve().parent
        for parent in (current, *current.parents):
            if (parent / "hscredit_studio").is_dir():
                return parent
        raise SandboxError("无法定位 backend 项目根目录")

    async def execute(self, node_type: str, inputs: dict, params: dict) -> dict:
        worker_path = self._project_root / self.WORKER_RELATIVE_PATH
        if not worker_path.exists():
            raise SandboxError(f"沙箱 worker 脚本不存在: {worker_path}")

        # 通过临时文件交换 pickle 数据 (避免命令行长度限制)
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as payload_file:
            pickle.dump({"node_type": node_type, "inputs": inputs, "params": params}, payload_file)
            payload_path = payload_file.name

        try:
            start = time.monotonic()
            try:
                proc = subprocess.run(
                    [sys.executable, str(worker_path), payload_path],
                    capture_output=True,
                    text=False,
                    timeout=self.timeout_sec,
                    cwd=str(self._project_root),
                )
            except subprocess.TimeoutExpired as e:
                duration = time.monotonic() - start
                _log.warning(
                    "sandbox_timeout",
                    node_type=node_type,
                    timeout_sec=self.timeout_sec,
                    duration_sec=round(duration, 2),
                )
                raise SandboxTimeoutError(
                    f"节点 {node_type} 执行超过 {self.timeout_sec}s 超时"
                ) from e

            duration = time.monotonic() - start

            if proc.returncode != 0:
                # worker 进程异常退出 (崩溃/未捕获异常)
                stderr = proc.stderr.decode("utf-8", errors="replace")[:2000]
                _log.error(
                    "sandbox_subprocess_failed",
                    node_type=node_type,
                    returncode=proc.returncode,
                    stderr=stderr,
                    duration_sec=round(duration, 2),
                )
                # 区分 OOM (Linux OOM killer 写 dmesg, returncode 通常 -9 / 137)
                if proc.returncode in (-9, 137):
                    raise SandboxOOMError(
                        f"节点 {node_type} 被 OOM killer 终止 (returncode={proc.returncode})"
                    )
                raise SandboxError(
                    f"节点 {node_type} 子进程异常退出 (returncode={proc.returncode}): {stderr}"
                )

            # 成功: stdout 是 pickle 序列化后的输出 dict
            try:
                result = pickle.loads(proc.stdout)
            except Exception as e:
                raise SandboxError(
                    f"节点 {node_type} 返回数据反序列化失败: {e}"
                ) from e

            if isinstance(result, dict) and result.get("__sandbox_error__"):
                # worker 捕获的业务异常
                err = result["__sandbox_error__"]
                code = err.get("code", "E_UNKNOWN")
                message = err.get("message", "未知错误")
                details = err.get("details", {})
                if code == "SANDBOX_TIMEOUT":
                    raise SandboxTimeoutError(message) from None
                if code == "SANDBOX_OOM":
                    raise SandboxOOMError(message) from None
                # 业务错误透传 (保留原类型名称)

                exc_cls_name = err.get("exception_type")
                if exc_cls_name:
                    # 不重建原异常类 (避免反射滥用), 直接抛 SandboxError 包装
                    raise SandboxError(f"{exc_cls_name}: {message} (details={details})") from None
                raise SandboxError(message) from None

            _log.info(
                "sandbox_subprocess_ok",
                node_type=node_type,
                duration_sec=round(duration, 2),
                outputs_count=len(result) if isinstance(result, dict) else 0,
            )
            return result  # type: ignore[return-value]

        finally:
            with contextlib.suppress(OSError):
                os.unlink(payload_path)


class DockerSandbox(SandboxBackend):
    """Docker 沙箱占位实现.

    B14 当前迭代: 占位, 抛 ``NotImplementedError``。
    B14 后续迭代: 调用 ``docker run --rm --memory=... --cpus=... hscredit-sandbox:latest``。
    """

    async def execute(self, node_type: str, inputs: dict, params: dict) -> dict:
        raise NotImplementedError(
            "DockerSandbox 将在 B14 后续迭代实现, 当前请使用 sandbox_backend=subprocess"
        )


# ===== 后端选择 =====


_backend: SandboxBackend | None = None


def get_sandbox_backend() -> SandboxBackend:
    """获取沙箱后端单例.

    根据 :attr:`Settings.sandbox_backend` 选择, ``SANDBOX_ENABLED=False`` 时回退到 InProcess。
    """
    global _backend
    if _backend is not None:
        return _backend

    if not settings.sandbox_enabled:
        _log.info("sandbox_disabled_fallback_inprocess")
        _backend = InProcessSandbox()
        return _backend

    backend_name = settings.sandbox_backend.lower()
    if backend_name == "subprocess":
        _backend = SubprocessSandbox()
    elif backend_name == "docker":
        _backend = DockerSandbox()
    elif backend_name == "inprocess":
        _backend = InProcessSandbox()
    else:
        _log.warning("sandbox_backend_unknown_fallback_subprocess", backend=backend_name)
        _backend = SubprocessSandbox()
    return _backend


def reset_sandbox_backend() -> None:
    """重置沙箱后端 (用于测试切换 / 配置热更新)."""
    global _backend
    _backend = None


__all__ = [
    "DockerSandbox",
    "InProcessSandbox",
    "SandboxBackend",
    "SandboxError",
    "SandboxOOMError",
    "SandboxTimeoutError",
    "SubprocessSandbox",
    "get_sandbox_backend",
    "reset_sandbox_backend",
]
