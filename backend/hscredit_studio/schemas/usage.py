"""用量查询 Schema — Phase 4 B18.

依据 docs/ROADMAP.md Phase 4 B18:

> 提供 GET /api/v1/{tenant}/usage?from=&to= API, 按 Run / Sandbox / Storage / API Call 分维度返回。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NodeTypeUsage(BaseModel):
    """按节点类型聚合的用量."""

    model_config = ConfigDict(from_attributes=True)

    node_type: str
    runs: int = Field(description="执行次数")
    total_duration_ms: int = Field(description="累计耗时 (毫秒)")


class DimensionUsage(BaseModel):
    """单个维度的用量汇总."""

    total: int = Field(default=0, description="该维度的总计数")
    success_count: int = Field(default=0, description="成功数 (Run 维度)")
    failed_count: int = Field(default=0, description="失败数 (Run 维度)")
    active_count: int = Field(default=0, description="活跃数 (Run 维度)")
    total_bytes: int = Field(default=0, description="总大小 (Artifact 维度, 字节)")
    total_duration_ms: int = Field(default=0, description="总耗时 (Sandbox 维度, 毫秒)")
    total_cpu_seconds: float = Field(default=0.0, description="总 CPU 时间 (Sandbox 维度, 秒)")
    max_mem_peak_mb: float = Field(default=0.0, description="峰值内存 (Sandbox 维度, MB)")
    by_node_type: list[NodeTypeUsage] = Field(
        default_factory=list, description="按节点类型聚合 (Sandbox 维度)"
    )


class TenantUsageResponse(BaseModel):
    """租户用量汇总 — Phase 4 B18 验收响应."""

    tenant_id: UUID
    range_start: datetime = Field(description="起始时间")
    range_end: datetime = Field(description="截止时间")
    runs: DimensionUsage = Field(description="Run 维度")
    sandbox: DimensionUsage = Field(description="Sandbox 执行维度")
    artifacts: DimensionUsage = Field(description="Artifact 维度")
    workflows: DimensionUsage = Field(description="Workflow 维度")
    api_calls: DimensionUsage = Field(description="API 调用维度 (Phase 7 引入)")


__all__ = [
    "DimensionUsage",
    "NodeTypeUsage",
    "TenantUsageResponse",
]
