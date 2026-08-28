"""BI 报表导出 Schemas — Phase 7 B33.

依据 docs/ROADMAP.md Phase 7 B33:

> 支持导出 BI 引擎格式: CSV / Parquet / 数据库视图 / API streaming
> PowerBI / Tableau 直连示例
> 帆软 FineBI 模板 (中文客户)
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class BIExportFormat(StrEnum):
    """BI 导出格式枚举 (Phase 7 B33)."""

    CSV = "csv"
    JSON = "json"          # streaming NDJSON
    PARQUET = "parquet"    # 二进制 (依赖 pandas+pyarrow)


class BIDatasetKey(StrEnum):
    """BI 数据集枚举 — 平台内可导出的核心数据集."""

    AUDIT_EVENTS = "audit_events"          # 审计事件
    RUNS = "runs"                          # 工作流运行
    NODE_EXECUTIONS = "node_executions"    # 节点执行
    BILLING = "billing"                    # 账单
    USAGE_DAILY = "usage_daily"            # 用量按日
    ALERT_HISTORY = "alert_history"        # 告警历史


class BIDatasetInfo(BaseModel):
    """BI 数据集元信息 (B33)."""

    key: BIDatasetKey
    name: str
    description: str
    fields: list[str]
    estimated_rows: int
    supports_streaming: bool = True
    supports_parquet: bool = True


class BIDatasetListResponse(BaseModel):
    """BI 数据集列表响应."""

    items: list[BIDatasetInfo]
    total: int


class BIExportRequest(BaseModel):
    """BI 导出请求 (B33 验收)."""

    dataset: BIDatasetKey
    format: BIExportFormat = BIExportFormat.CSV
    since: datetime | None = None
    until: datetime | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(10000, ge=1, le=1_000_000)


class BIExportResponse(BaseModel):
    """BI 导出响应 (B33 验收)."""

    dataset: BIDatasetKey
    format: BIExportFormat
    filename: str
    media_type: str
    row_count: int
    generated_at: datetime
    download_path: str = Field(..., description="服务端流式下载路径")


class BIViewInfo(BaseModel):
    """BI 数据库视图信息."""

    name: str
    schema_name: str = Field(..., alias="schema", description="数据库 schema")
    description: str
    columns: list[str]

    model_config = {"populate_by_name": True}


class BIViewListResponse(BaseModel):
    """BI 数据库视图列表响应."""

    items: list[BIViewInfo]
    total: int


# ===== BI 工具连接模板 (B33) =====


class PowerBIQueryInfo(BaseModel):
    """PowerBI 单个查询定义."""

    name: str
    display_name: str
    m_query: str = Field(..., description="Power Query M 语言查询")
    description: str = ""


class PowerBITemplateResponse(BaseModel):
    """PowerBI 直连模板 (B33 验收)."""

    tenant_id: str
    tenant_slug: str
    base_url: str
    protocol: str = "https"
    auth_method: str = "bearer_token"
    queries: list[PowerBIQueryInfo]
    import_instructions: str
    raw_config: dict[str, Any]


class TableauConnectionInfo(BaseModel):
    """Tableau 数据源连接信息."""

    server: str
    port: int = 5432
    database: str
    username: str
    use_ssl: bool = True


class TableauTemplateResponse(BaseModel):
    """Tableau .tds 直连模板 (B33 验收)."""

    tenant_id: str
    tenant_slug: str
    connection: TableauConnectionInfo
    schema_xml: str = Field(..., description="Tableau .tds 格式 (XML)")
    import_instructions: str


class FineBITableInfo(BaseModel):
    """FineBI 数据表定义."""

    table_name: str
    display_name: str
    description: str
    sql: str = Field(..., description="FineBI 抽取 SQL")
    fields: list[str]


class FineBITemplateResponse(BaseModel):
    """帆软 FineBI 模板 (B33 验收 - 中文客户)."""

    tenant_id: str
    tenant_slug: str
    display_name_zh: str
    display_name_en: str
    tables: list[FineBITableInfo]
    config_xml: str = Field(..., description="FineBI 数据包配置 XML")
    import_instructions_zh: str


# ===== 连接器测试 =====


class ConnectorTestResponse(BaseModel):
    """BI 连接器连通性测试响应."""

    connector: str  # powerbi / tableau / finebi
    healthy: bool
    message: str
    tested_at: datetime


__all__ = [
    "BIDatasetInfo",
    "BIDatasetKey",
    "BIDatasetListResponse",
    "BIExportFormat",
    "BIExportRequest",
    "BIExportResponse",
    "BIViewInfo",
    "BIViewListResponse",
    "ConnectorTestResponse",
    "FineBITableInfo",
    "FineBITemplateResponse",
    "PowerBIQueryInfo",
    "PowerBITemplateResponse",
    "TableauConnectionInfo",
    "TableauTemplateResponse",
]
