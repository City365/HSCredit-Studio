"""Phase 3 B17 沙箱资源用量埋点 — 单元测试.

依据 docs/ROADMAP.md Phase 3 B17 验收:

- SandboxResourceUsage dataclass 字段正确
- SubprocessSandbox.execute_with_usage 返回 (outputs, usage)
- usage.duration_ms > 0
- usage.status == "success" (正常路径) / "timeout" (超时路径)
- InProcessSandbox.execute_with_usage 同等行为

注: 不连真实 DB 测 record_resource_usage (那是 E2E 范畴)。
"""
from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import pytest

from hscredit_studio.services.sandbox import (
    InProcessSandbox,
    SandboxResourceUsage,
    SandboxTimeoutError,
    SubprocessSandbox,
)


@pytest.fixture
def sample_csv():
    """创建临时 CSV 文件."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("id,name\n")
        f.write("1,Alice\n")
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_sandbox_resource_usage_dataclass():
    """SandboxResourceUsage: 默认值 + 字段."""
    u = SandboxResourceUsage()
    assert u.cpu_seconds == 0.0
    assert u.mem_peak_mb == 0.0
    assert u.duration_ms == 0
    assert u.status == "success"


def test_sandbox_resource_usage_custom_values():
    """SandboxResourceUsage: 自定义值."""
    u = SandboxResourceUsage(cpu_seconds=2.5, mem_peak_mb=512.0, duration_ms=2500, status="timeout")
    assert u.cpu_seconds == 2.5
    assert u.mem_peak_mb == 512.0
    assert u.duration_ms == 2500
    assert u.status == "timeout"


@pytest.mark.asyncio
async def test_subprocess_sandbox_execute_with_usage_success(sample_csv):
    """SubprocessSandbox.execute_with_usage: 成功路径返回 (outputs, usage)."""
    from hscredit_studio.nodes.data_ingest.csv_ingest import CSVIngestNode
    from hscredit_studio.nodes.registry import NodeRegistry

    NodeRegistry.clear()
    NodeRegistry.register(CSVIngestNode)

    sandbox = SubprocessSandbox(timeout_sec=60)
    outputs, usage = await sandbox.execute_with_usage(
        "csv_ingest",
        inputs={},
        params={"path": sample_csv, "sep": ",", "encoding": "utf-8"},
    )

    assert "df" in outputs
    assert isinstance(usage, SandboxResourceUsage)
    assert usage.duration_ms > 0
    assert usage.status == "success"


@pytest.mark.asyncio
async def test_subprocess_sandbox_execute_with_usage_timeout():
    """SubprocessSandbox.execute_with_usage: 超时路径 usage.status='timeout'."""
    from hscredit_studio.nodes.data_ingest.csv_ingest import CSVIngestNode
    from hscredit_studio.nodes.registry import NodeRegistry

    NodeRegistry.clear()
    NodeRegistry.register(CSVIngestNode)

    import time as _time

    def _loop(*args, **kwargs):
        _time.sleep(10)
        return {}

    with patch.object(CSVIngestNode, "run", _loop):
        sandbox = SubprocessSandbox(timeout_sec=2)
        with pytest.raises(SandboxTimeoutError):
            await sandbox.execute_with_usage(
                "csv_ingest",
                inputs={},
                params={"path": "dummy.csv", "sep": ",", "encoding": "utf-8"},
            )


@pytest.mark.asyncio
async def test_subprocess_sandbox_execute_with_usage_failure():
    """SubprocessSandbox.execute_with_usage: ValidationError 路径 status='failed'."""
    from hscredit_studio.nodes.data_ingest.csv_ingest import CSVIngestNode
    from hscredit_studio.nodes.registry import NodeRegistry

    NodeRegistry.clear()
    NodeRegistry.register(CSVIngestNode)

    sandbox = SubprocessSandbox(timeout_sec=10)
    from hscredit_studio.services.sandbox import SandboxError

    with pytest.raises(SandboxError):
        _, _ = await sandbox.execute_with_usage(
            "csv_ingest",
            inputs={},
            params={"path": ""},  # 触发 ValidationError
        )


@pytest.mark.asyncio
async def test_inprocess_sandbox_execute_with_usage_success(sample_csv):
    """InProcessSandbox.execute_with_usage: 返回 (outputs, usage)."""
    from hscredit_studio.nodes.data_ingest.csv_ingest import CSVIngestNode
    from hscredit_studio.nodes.registry import NodeRegistry

    NodeRegistry.clear()
    NodeRegistry.register(CSVIngestNode)

    sandbox = InProcessSandbox()
    outputs, usage = await sandbox.execute_with_usage(
        "csv_ingest",
        inputs={},
        params={"path": sample_csv, "sep": ",", "encoding": "utf-8"},
    )

    assert "df" in outputs
    assert isinstance(usage, SandboxResourceUsage)
    assert usage.duration_ms >= 0
    assert usage.status == "success"


@pytest.mark.asyncio
async def test_execute_returns_dict_backward_compat(sample_csv):
    """execute() 向后兼容: 返回 dict (与 B14 接口一致)."""
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
    assert isinstance(outputs, dict)
    assert "df" in outputs


def test_resource_usage_module_exports():
    """services.resource_usage 模块导出函数完整."""
    from hscredit_studio.services import resource_usage

    assert hasattr(resource_usage, "record_resource_usage")
    assert hasattr(resource_usage, "aggregate_by_tenant")
    assert callable(resource_usage.record_resource_usage)
    assert callable(resource_usage.aggregate_by_tenant)
