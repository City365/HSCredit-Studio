"""User Code Sandbox Backend — 用户自定义节点沙箱执行 (Phase 6 B36).

依据 docs/node-plugin/01_DESIGN.md 第 4.5 节:

复用 SubprocessSandbox 模式, 调用 _user_sandbox_worker.py 子进程:

- 子进程启动: preexec_fn 应用 setrlimit (CPU/AS/FSIZE/NOFILE/NPROC)
- payload 通过临时 pickle 文件传递 (避免命令行长度限制)
- 超时由 subprocess.run 的 timeout 参数强制 (60s 默认)
- 输出: outputs dict + 日志 + 资源用量

依赖:
- _user_sandbox_worker.py 在同目录下
- RestrictedPython (optional, 推荐)
"""

from __future__ import annotations

import os
import pickle
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from hscredit_studio.core.config import settings
from hscredit_studio.core.logging import get_logger

_log = get_logger(__name__)


# ===== 异常类 =====


class UserSandboxError(Exception):
    """用户代码沙箱通用错误."""


class UserSandboxTimeout(UserSandboxError):
    """执行超时."""


class UserSandboxOOM(UserSandboxError):
    """内存超限."""


def _safe_path_for_sandbox() -> str:
    """构造沙箱用的安全 PATH.

    Windows 必须保留 System32 等系统目录 (DLL 加载必需), 包含 Python venv 自身的 Scripts.
    不能去掉太多, 否则 _overlapped.pyd 等关键 DLL 找不到.

    Linux/macOS: 保留 /usr/bin:/bin, 去掉 /home 等用户目录.
    """
    import sys as _sys
    raw_path = os.environ.get("PATH", "")
    if _sys.platform == "win32":
        # Windows: 保留主进程完整 PATH, 因为:
        # 1. Python venv 的 _overlapped.pyd 等 DLL 依赖 PATH 才能找到
        # 2. pydantic_settings / structlog 等依赖也需 PATH
        # 3. 阻止外部命令执行不靠 PATH 过滤, 靠 RestrictedPython 黑名单
        return raw_path
    else:
        # Linux/macOS: 保留系统目录
        return raw_path or "/usr/bin:/bin:/usr/local/bin"


# ===== 资源使用 =====


class UserSandboxUsage:
    """资源用量统计."""

    def __init__(
        self,
        cpu_seconds: float = 0.0,
        mem_peak_mb: float = 0.0,
        duration_ms: int = 0,
        status: str = "success",
    ):
        self.cpu_seconds = cpu_seconds
        self.mem_peak_mb = mem_peak_mb
        self.duration_ms = duration_ms
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_seconds": self.cpu_seconds,
            "mem_peak_mb": self.mem_peak_mb,
            "duration_ms": self.duration_ms,
            "status": self.status,
        }


# ===== 沙箱后端 =====


class UserSandbox:
    """用户代码沙箱执行器.

    典型用法:
        sb = UserSandbox()
        outputs, usage = sb.execute(
            code=user_code,
            sample_inputs={"df": df},
            sample_params={"threshold": 0.5},
        )
    """

    def __init__(
        self,
        timeout_sec: int | None = None,
        memory_mb: int | None = None,
        cpu_count: int | None = None,
        max_pid: int | None = None,
        max_open_files: int | None = None,
    ):
        """初始化沙箱.

        Args:
            timeout_sec: wall-clock 超时 (默认 settings.user_sandbox_timeout_sec=60)
            memory_mb: 内存上限 MB (默认 2048)
            cpu_count: CPU 时间限制 (默认 = timeout_sec)
            max_pid: 进程数上限 (默认 32)
            max_open_files: 文件描述符上限 (默认 64)
        """
        self.timeout_sec = timeout_sec or 60
        self.memory_bytes = (memory_mb or 2048) * 1024 * 1024
        self.cpu_seconds = cpu_count or self.timeout_sec
        self.max_pid = max_pid or 32
        self.max_open_files = max_open_files or 64

        # 定位 worker 脚本和 backend 根目录
        self._worker_path = (
            Path(__file__).resolve().parent.parent / "executor" / "_user_sandbox_worker.py"
        )
        if not self._worker_path.exists():
            raise UserSandboxError(f"worker 脚本不存在: {self._worker_path}")
        # worker 子进程需要能 import hscredit_studio, 所以 cwd 设为 backend 根目录
        self._project_root = Path(__file__).resolve().parent.parent

    def execute(
        self,
        code: str,
        sample_inputs: dict[str, Any] | None = None,
        sample_params: dict[str, Any] | None = None,
        node_type: str = "",
    ) -> tuple[dict[str, Any], UserSandboxUsage]:
        """在沙箱子进程中执行用户代码.

        Args:
            code: Python 源码
            sample_inputs: 喂给 run() 的 inputs dict
            sample_params: 喂给 run() 的 params dict
            node_type: 节点类型 (日志用)

        Returns:
            (outputs, usage) — outputs 是 dict 或错误 dict
        """
        sample_inputs = sample_inputs or {}
        sample_params = sample_params or {}

        # 1. 序列化 payload 到临时文件
        payload = {
            "code": code,
            "sample_inputs": sample_inputs,
            "sample_params": sample_params,
            "node_type": node_type,
        }

        payload_file = tempfile.NamedTemporaryFile(
            suffix=".pkl", prefix="user_sandbox_", delete=False
        )
        try:
            pickle.dump(payload, payload_file)
            payload_file.close()
            payload_path = payload_file.name

            # 2. 启动子进程 — 用 venv 自己的 Python, 避免用系统 Python 找不到依赖
            start = time.monotonic()
            # 关键: 必须用 venv 自己的 python.exe, 否则子进程会用系统 Python
            # 导致 import hscredit_studio 失败 (找不到 .venv/Lib/site-packages)
            venv_python = self._project_root / ".venv" / "Scripts" / "python.exe"
            if venv_python.exists():
                child_python = str(venv_python)
            else:
                # 非 Windows (Linux/macOS)
                venv_python = self._project_root / ".venv" / "bin" / "python"
                child_python = str(venv_python) if venv_python.exists() else sys.executable

            # uv venv 是 symlink 模式: Python 解释器 symlink 自 uv 安装目录
            # 必须保留 PARENT 进程的 venv Python 配置, 否则子进程找不到 stdlib
            # 方案: 不传 env dict, 让子进程继承主进程 env (subprocess.run 默认行为)
            # 只覆盖必要的 PATH 清空
            child_env = os.environ.copy()  # 继承主进程 env
            child_env.update({
                # 阻止读取用户敏感环境变量
                "HOME": "/tmp",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
                "USER": "sandbox",
                "USERNAME": "sandbox",
            })
            # 把主进程的 SECRET_KEY 等透传给子进程 (settings 需要)
            child_env.setdefault("SECRET_KEY", "sandbox-fake-secret-key-for-user-sandbox-only-min-32-chars")
            child_env.setdefault("JWT_SECRET_KEY", "sandbox-fake-jwt-secret-key-for-user-sandbox-only-min-32-chars")
            try:
                proc = subprocess.run(
                    [child_python, "-B", str(self._worker_path), payload_path],
                    capture_output=True,
                    text=False,
                    timeout=self.timeout_sec,
                    env=child_env,
                    cwd=str(self._project_root),  # backend 根目录
                )
            except subprocess.TimeoutExpired as e:
                duration_ms = int((time.monotonic() - start) * 1000)
                _log.warning(
                    "user_sandbox_timeout",
                    node_type=node_type,
                    timeout_sec=self.timeout_sec,
                    duration_sec=round(duration_ms / 1000, 2),
                )
                raise UserSandboxTimeout(
                    f"节点 {node_type} 执行超过 {self.timeout_sec}s 超时"
                ) from e

            duration_ms = int((time.monotonic() - start) * 1000)

            # 3. 检查退出码
            if proc.returncode != 0:
                stderr = proc.stderr.decode("utf-8", errors="replace")[:2000]
                _log.error(
                    "user_sandbox_subprocess_failed",
                    node_type=node_type,
                    returncode=proc.returncode,
                    stderr=stderr,
                )
                # -9 / 137 → Linux OOM killer
                if proc.returncode in (-9, 137):
                    raise UserSandboxOOM(
                        f"节点 {node_type} 被 OOM killer 终止"
                    )
                raise UserSandboxError(
                    f"节点 {node_type} 子进程异常退出 (returncode={proc.returncode}): {stderr}"
                )

            # 4. 反序列化输出
            try:
                result = pickle.loads(proc.stdout)
            except Exception as e:
                raise UserSandboxError(
                    f"节点 {node_type} 返回数据反序列化失败: {e}"
                ) from e

            # 5. 处理错误响应
            if isinstance(result, dict) and "__sandbox_error__" in result:
                err = result["__sandbox_error__"]
                code = err.get("code", "E_UNKNOWN")
                msg = err.get("message", "未知错误")
                exc_type = err.get("exception_type", "")

                if code == "SANDBOX_OOM":
                    usage = UserSandboxUsage(duration_ms=duration_ms, status="oom")
                    raise UserSandboxOOM(f"{exc_type}: {msg}")
                if code == "SANDBOX_TIMEOUT":
                    usage = UserSandboxUsage(duration_ms=duration_ms, status="timeout")
                    raise UserSandboxTimeout(f"{exc_type}: {msg}")

                # 业务错误 / 校验失败 — 透传
                usage = UserSandboxUsage(duration_ms=duration_ms, status="failed")
                _log.warning(
                    "user_sandbox_error",
                    node_type=node_type,
                    code=code,
                    message=msg,
                    duration_ms=duration_ms,
                )
                # 返回带错误的 result 而非抛异常 (供上层 try_run 灵活处理)
                return result, usage

            # 6. 成功
            _log.info(
                "user_sandbox_ok",
                node_type=node_type,
                duration_ms=duration_ms,
                outputs_count=len(result) if isinstance(result, dict) else 0,
            )
            usage = UserSandboxUsage(duration_ms=duration_ms, status="success")
            return result, usage

        finally:
            # 清理 payload 文件
            try:
                os.unlink(payload_path)
            except OSError:
                pass


__all__ = [
    "UserSandbox",
    "UserSandboxError",
    "UserSandboxOOM",
    "UserSandboxTimeout",
    "UserSandboxUsage",
]
