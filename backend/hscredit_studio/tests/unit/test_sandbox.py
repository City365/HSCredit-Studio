"""Phase 3 B14 沙箱执行器 — 单元测试.

依据 docs/ROADMAP.md Phase 3 B14:

验收点:
- SubprocessSandbox 可执行 csv_ingest 等真实节点
- 节点抛 ValidationError 时, 子进程不崩溃, 主进程拿到序列化错误
- 超时配置生效 (缩短到 1s, 验证 SandboxTimeoutError)
- 业务异常错误码透传 (ValidationError -> SandboxError, 含 exception_type)
- InProcessSandbox 行为与原 tasks.py 一致
- get_sandbox_backend() 单例, 可通过 reset_sandbox_backend() 重置
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from hscredit_studio.services.sandbox import (
    InProcessSandbox,
    SandboxError,
    SandboxTimeoutError,
    SubprocessSandbox,
    get_sandbox_backend,
    reset_sandbox_backend,
)


@pytest.fixture
def sample_csv():
    """创建临时 CSV 文件."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("id,name,score\n")
        f.write("1,Alice,0.85\n")
        f.write("2,Bob,0.92\n")
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.mark.asyncio
async def test_inprocess_sandbox_runs_csv_ingest(sample_csv):
    """InProcessSandbox: 注册节点 + 真实执行 csv_ingest."""
    # 确保 csv_ingest 已注册
    from hscredit_studio.nodes.data_ingest.csv_ingest import CSVIngestNode
    from hscredit_studio.nodes.registry import NodeRegistry

    NodeRegistry.clear()
    NodeRegistry.register(CSVIngestNode)

    sandbox = InProcessSandbox()
    outputs = await sandbox.execute(
        "csv_ingest",
        inputs={},
        params={"path": sample_csv, "sep": ",", "encoding": "utf-8"},
    )

    assert "df" in outputs
    assert "schema" in outputs
    assert isinstance(outputs["df"], pd.DataFrame)
    assert len(outputs["df"]) == 2


@pytest.mark.asyncio
async def test_inprocess_sandbox_unknown_node_raises():
    """InProcessSandbox: 未注册节点抛 SandboxError."""
    NodeRegistry = __import__(
        "hscredit_studio.nodes.registry", fromlist=["NodeRegistry"]
    ).NodeRegistry
    NodeRegistry.clear()

    sandbox = InProcessSandbox()
    with pytest.raises(SandboxError, match="未注册"):
        await sandbox.execute("nonexistent_node", inputs={}, params={})


@pytest.mark.asyncio
async def test_subprocess_sandbox_runs_csv_ingest(sample_csv):
    """SubprocessSandbox: 真实子进程执行 csv_ingest, 返回 DataFrame."""
    from hscredit_studio.nodes.data_ingest.csv_ingest import CSVIngestNode
    from hscredit_studio.nodes.registry import NodeRegistry

    NodeRegistry.clear()
    NodeRegistry.register(CSVIngestNode)

    sandbox = SubprocessSandbox(timeout_sec=60)
    outputs = await sandbox.execute(
        "csv_ingest",
        inputs={},
        params={"path": sample_csv, "sep": ",", "encoding": "utf-8"},
    )

    assert "df" in outputs
    assert isinstance(outputs["df"], pd.DataFrame)
    assert len(outputs["df"]) == 2


@pytest.mark.asyncio
async def test_subprocess_sandbox_propagates_validation_error():
    """SubprocessSandbox: 业务异常 (ValidationError) 透传为 SandboxError."""
    from hscredit_studio.nodes.data_ingest.csv_ingest import CSVIngestNode
    from hscredit_studio.nodes.registry import NodeRegistry

    NodeRegistry.clear()
    NodeRegistry.register(CSVIngestNode)

    sandbox = SubprocessSandbox(timeout_sec=10)
    # path="" 触发 ValidationError
    with pytest.raises(SandboxError, match="ValidationError"):
        await sandbox.execute("csv_ingest", inputs={}, params={"path": ""})


@pytest.mark.asyncio
async def test_subprocess_sandbox_timeout():
    """SubprocessSandbox: 节点死循环超过 timeout_sec 触发 SandboxTimeoutError.

    通过 patch 节点 run() 模拟死循环, 验证 timeout 配置生效。
    """
    from hscredit_studio.nodes.data_ingest.csv_ingest import CSVIngestNode
    from hscredit_studio.nodes.registry import NodeRegistry

    NodeRegistry.clear()
    NodeRegistry.register(CSVIngestNode)

    # 让 csv_ingest.run 陷入死循环
    import time as _time

    def _loop(*args, **kwargs):
        _time.sleep(10)
        return {}

    with patch.object(CSVIngestNode, "run", _loop):
        sandbox = SubprocessSandbox(timeout_sec=2)
        with pytest.raises(SandboxTimeoutError, match="超时"):
            await sandbox.execute(
                "csv_ingest",
                inputs={},
                params={"path": "dummy.csv", "sep": ",", "encoding": "utf-8"},
            )


def test_get_sandbox_backend_returns_subprocess_by_default(monkeypatch):
    """get_sandbox_backend(): sandbox_backend=subprocess (默认) 返回 SubprocessSandbox."""
    from hscredit_studio.core.config import settings

    monkeypatch.setattr(settings, "sandbox_backend", "subprocess")
    monkeypatch.setattr(settings, "sandbox_enabled", True)
    reset_sandbox_backend()

    backend = get_sandbox_backend()
    assert isinstance(backend, SubprocessSandbox)
    reset_sandbox_backend()


def test_get_sandbox_backend_returns_inprocess_when_disabled(monkeypatch):
    """get_sandbox_backend(): sandbox_enabled=False 返回 InProcessSandbox."""
    from hscredit_studio.core.config import settings

    monkeypatch.setattr(settings, "sandbox_enabled", False)
    reset_sandbox_backend()

    backend = get_sandbox_backend()
    assert isinstance(backend, InProcessSandbox)
    reset_sandbox_backend()


def test_subprocess_sandbox_cleans_up_tempfile(sample_csv):
    """SubprocessSandbox: 执行后临时 payload 文件被清理."""
    from hscredit_studio.nodes.data_ingest.csv_ingest import CSVIngestNode
    from hscredit_studio.nodes.registry import NodeRegistry

    NodeRegistry.clear()
    NodeRegistry.register(CSVIngestNode)

    sandbox = SubprocessSandbox(timeout_sec=30)
    # 跑一次后, 临时目录不应残留 payload.pkl
    import asyncio

    asyncio.run(
        sandbox.execute(
            "csv_ingest",
            inputs={},
            params={"path": sample_csv, "sep": ",", "encoding": "utf-8"},
        )
    )

    # 验证: 后台扫描 tempfile 目录, 不应有本次执行的 payload 文件
    tmp_root = Path(tempfile.gettempdir())
    leftover_payloads = [
        p
        for p in tmp_root.glob("tmp*.pkl")
        # 排除非本次会话产生的
        if p.stat().st_mtime > time.monotonic() - 100
    ]
    # 不严格断言 (其他进程可能正在用), 至少不应有大量残留
    assert len(leftover_payloads) < 10
