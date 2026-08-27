"""Phase 4 B18 用量查询 Schema — 单元测试."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from hscredit_studio.schemas.usage import (
    DimensionUsage,
    NodeTypeUsage,
    TenantUsageResponse,
)


def test_dimension_usage_defaults():
    """DimensionUsage: 所有字段默认值."""
    d = DimensionUsage()
    assert d.total == 0
    assert d.total_bytes == 0
    assert d.total_duration_ms == 0
    assert d.total_cpu_seconds == 0.0
    assert d.max_mem_peak_mb == 0.0
    assert d.by_node_type == []


def test_node_type_usage_required():
    """NodeTypeUsage: 必填字段缺失报错."""
    with pytest.raises(ValidationError):
        NodeTypeUsage()  # 缺 node_type / runs / total_duration_ms


def test_node_type_usage_valid():
    """NodeTypeUsage: 正常创建."""
    n = NodeTypeUsage(node_type="csv_ingest", runs=10, total_duration_ms=5000)
    assert n.node_type == "csv_ingest"
    assert n.runs == 10
    assert n.total_duration_ms == 5000


def test_tenant_usage_response_round_trip():
    """TenantUsageResponse: 创建 + 序列化."""
    tid = UUID("12345678-1234-5678-1234-567812345678")
    r = TenantUsageResponse(
        tenant_id=tid,
        range_start=datetime(2026, 1, 1),
        range_end=datetime(2026, 1, 31),
        runs=DimensionUsage(total=10, success_count=8, failed_count=1, active_count=1),
        sandbox=DimensionUsage(
            total=10,
            total_duration_ms=50000,
            total_cpu_seconds=12.5,
            max_mem_peak_mb=512.0,
        ),
        artifacts=DimensionUsage(total=5, total_bytes=1048576),
        workflows=DimensionUsage(total=3),
        api_calls=DimensionUsage(total=0),
    )
    j = r.model_dump_json()
    parsed = TenantUsageResponse.model_validate_json(j)
    assert parsed.tenant_id == tid
    assert parsed.runs.success_count == 8
    assert parsed.sandbox.total_cpu_seconds == 12.5
    assert parsed.artifacts.total_bytes == 1048576
