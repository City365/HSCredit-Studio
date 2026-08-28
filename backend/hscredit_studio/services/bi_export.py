"""BI 报表导出服务 — Phase 7 B33.

依据 docs/ROADMAP.md Phase 7 B33:

> 支持导出 BI 引擎格式: CSV / Parquet / 数据库视图 / API streaming
> PowerBI / Tableau 直连示例
> 帆软 FineBI 模板 (中文客户)

设计要点:

- :class:`BIDatasetKey` 枚举可用数据集
- :func:`iter_dataset_csv` 流式 CSV (UTF-8 BOM, 大数据集友好)
- :func:`iter_dataset_json` 流式 NDJSON
- :func:`render_dataset_parquet` Parquet 二进制 (依赖 pandas+pyarrow)
- :func:`generate_powerbi_template` PowerBI 直连 JSON 模板
- :func:`generate_tableau_template` Tableau .tds XML
- :func:`generate_finebi_template` 帆软 FineBI XML (中文)
- :func:`list_bi_views` BI 数据库视图清单
"""
from __future__ import annotations

import csv
import io
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.logging import get_logger
from hscredit_studio.models import AuditEvent, Bill, Run
from hscredit_studio.schemas.bi_export import (
    BIDatasetInfo,
    BIDatasetKey,
    BIViewInfo,
    FineBITableInfo,
    PowerBIQueryInfo,
    TableauConnectionInfo,
)

_log = get_logger(__name__)


# ===== 数据集元信息 =====


@dataclass
class DatasetSpec:
    """数据集规范 (Phase 7 B33)."""

    key: BIDatasetKey
    name: str
    description: str
    fields: list[str]
    supports_parquet: bool = True


DATASETS: dict[str, DatasetSpec] = {
    BIDatasetKey.AUDIT_EVENTS.value: DatasetSpec(
        key=BIDatasetKey.AUDIT_EVENTS,
        name="审计事件",
        description="租户级审计事件流 (append-only, 7 年保留)",
        fields=[
            "event_id",
            "tenant_id",
            "user_id",
            "action",
            "resource_type",
            "resource_id",
            "ip_address",
            "occurred_at",
        ],
        supports_parquet=True,
    ),
    BIDatasetKey.RUNS.value: DatasetSpec(
        key=BIDatasetKey.RUNS,
        name="工作流运行",
        description="租户 Run 执行记录 (含耗时/状态/节点数)",
        fields=[
            "run_id",
            "workflow_id",
            "workflow_version_id",
            "run_number",
            "status",
            "started_at",
            "finished_at",
            "duration_ms",
        ],
        supports_parquet=True,
    ),
    BIDatasetKey.NODE_EXECUTIONS.value: DatasetSpec(
        key=BIDatasetKey.NODE_EXECUTIONS,
        name="节点执行",
        description="节点级执行明细 (用于性能分析)",
        fields=[
            "exec_id",
            "run_id",
            "node_id",
            "status",
            "started_at",
            "finished_at",
            "duration_ms",
            "retry_count",
        ],
        supports_parquet=True,
    ),
    BIDatasetKey.BILLING.value: DatasetSpec(
        key=BIDatasetKey.BILLING,
        name="账单",
        description="租户账单记录 (含基础费 + 三维超量费)",
        fields=[
            "bill_id",
            "tenant_id",
            "billing_period",
            "plan",
            "status",
            "base_fee",
            "overage_runs_fee",
            "overage_duration_fee",
            "overage_storage_fee",
            "total_amount",
            "currency",
            "due_date",
        ],
        supports_parquet=True,
    ),
    BIDatasetKey.USAGE_DAILY.value: DatasetSpec(
        key=BIDatasetKey.USAGE_DAILY,
        name="用量按日聚合",
        description="按日聚合的 Run/Storage/Sandbox 用量",
        fields=[
            "date",
            "tenant_id",
            "runs_count",
            "duration_ms",
            "storage_bytes",
        ],
        supports_parquet=True,
    ),
    BIDatasetKey.ALERT_HISTORY.value: DatasetSpec(
        key=BIDatasetKey.ALERT_HISTORY,
        name="告警历史",
        description="监控告警事件 (Phase 5 B27)",
        fields=[
            "alert_id",
            "rule_id",
            "tenant_id",
            "severity",
            "status",
            "started_at",
            "resolved_at",
        ],
        supports_parquet=True,
    ),
}


def list_datasets() -> list[BIDatasetInfo]:
    """列出所有可用 BI 数据集."""
    return [
        BIDatasetInfo(
            key=spec.key,
            name=spec.name,
            description=spec.description,
            fields=spec.fields,
            estimated_rows=-1,  # 实际值需运行后统计
            supports_streaming=True,
            supports_parquet=spec.supports_parquet,
        )
        for spec in DATASETS.values()
    ]


# ===== 流式 CSV / JSON =====


async def iter_dataset_csv(
    session: AsyncSession,
    dataset: BIDatasetKey,
    tenant_id: UUID,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 10000,
    filters: dict[str, Any] | None = None,
) -> AsyncIterator[bytes]:
    """流式 CSV 字节生成器 (Phase 7 B33 验收).

    UTF-8 BOM, Excel 直接打开, 流式输出避免大表 OOM.
    """
    # BOM (让 Excel 正确识别 UTF-8)
    yield b"\xef\xbb\xbf"

    buf = io.StringIO()
    writer = csv.writer(buf)

    if dataset == BIDatasetKey.AUDIT_EVENTS:
        writer.writerow(DATASETS[dataset.value].fields)
        yield buf.getvalue().encode("utf-8")
        buf.seek(0)
        buf.truncate(0)

        stmt = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
        if since:
            stmt = stmt.where(AuditEvent.occurred_at >= since)
        if until:
            stmt = stmt.where(AuditEvent.occurred_at <= until)
        stmt = stmt.order_by(AuditEvent.occurred_at.desc()).limit(limit)

        rows = (await session.execute(stmt)).scalars().all()
        for r in rows:
            writer.writerow([
                str(r.event_id),
                str(r.tenant_id),
                str(r.user_id) if r.user_id else "",
                r.action,
                r.resource_type or "",
                str(r.resource_id) if r.resource_id else "",
                r.ip_address or "",
                r.occurred_at.isoformat() if r.occurred_at else "",
            ])
            yield buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate(0)

    elif dataset == BIDatasetKey.RUNS:
        writer.writerow(DATASETS[dataset.value].fields)
        yield buf.getvalue().encode("utf-8")
        buf.seek(0)
        buf.truncate(0)

        stmt = select(Run).where(Run.tenant_id == tenant_id)
        if since:
            stmt = stmt.where(Run.created_at >= since)
        if until:
            stmt = stmt.where(Run.created_at <= until)
        if filters.get("status"):
            stmt = stmt.where(Run.status == filters["status"])
        stmt = stmt.order_by(Run.created_at.desc()).limit(limit)

        rows = (await session.execute(stmt)).scalars().all()
        for r in rows:
            duration = (
                (r.finished_at - r.started_at).total_seconds() * 1000
                if r.started_at and r.finished_at
                else 0
            )
            writer.writerow([
                str(r.run_id),
                str(r.workflow_id),
                str(r.workflow_version_id),
                r.run_number,
                r.status,
                r.started_at.isoformat() if r.started_at else "",
                r.finished_at.isoformat() if r.finished_at else "",
                int(duration),
            ])
            yield buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate(0)

    elif dataset == BIDatasetKey.BILLING:
        writer.writerow(DATASETS[dataset.value].fields)
        yield buf.getvalue().encode("utf-8")
        buf.seek(0)
        buf.truncate(0)

        stmt = select(Bill).where(Bill.tenant_id == tenant_id)
        if since:
            stmt = stmt.where(Bill.created_at >= since)
        if until:
            stmt = stmt.where(Bill.created_at <= until)
        stmt = stmt.order_by(Bill.billing_period.desc()).limit(limit)

        rows = (await session.execute(stmt)).scalars().all()
        for b in rows:
            writer.writerow([
                str(b.bill_id),
                str(b.tenant_id),
                b.billing_period,
                b.plan,
                b.status,
                b.base_fee,
                b.overage_runs_fee,
                b.overage_duration_fee,
                b.overage_storage_fee,
                b.total_amount,
                b.currency,
                b.due_date.isoformat() if b.due_date else "",
            ])
            yield buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate(0)

    elif dataset == BIDatasetKey.USAGE_DAILY:
        # 用量按日聚合 (跨表 join 略, 这里从 audit/runs 简单聚合示例)
        writer.writerow(DATASETS[dataset.value].fields)
        yield buf.getvalue().encode("utf-8")
        buf.seek(0)
        buf.truncate(0)

        # 按日聚合 runs
        day_expr = func.date_trunc("day", Run.created_at).label("date")
        stmt = (
            select(
                day_expr,
                Run.tenant_id,
                func.count(Run.run_id).label("runs_count"),
                func.coalesce(
                    func.sum(
                        func.extract(
                            "epoch",
                            Run.finished_at - Run.started_at,
                        )
                        * 1000
                    ),
                    0,
                ).label("duration_ms"),
            )
            .where(Run.tenant_id == tenant_id)
            .group_by(day_expr, Run.tenant_id)
            .order_by(day_expr.desc())
            .limit(limit)
        )
        if since:
            stmt = stmt.where(Run.created_at >= since)
        if until:
            stmt = stmt.where(Run.created_at <= until)

        rows = (await session.execute(stmt)).all()
        for date, tid, runs_cnt, dur_ms in rows:
            writer.writerow([
                date.isoformat() if date else "",
                str(tid),
                int(runs_cnt or 0),
                int(dur_ms or 0),
                0,
            ])
            yield buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate(0)

    else:
        # 未实现的数据集: 写入表头+空行
        writer.writerow(DATASETS[dataset.value].fields)
        yield buf.getvalue().encode("utf-8")


async def iter_dataset_json(
    session: AsyncSession,
    dataset: BIDatasetKey,
    tenant_id: UUID,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 10000,
) -> AsyncIterator[bytes]:
    """流式 NDJSON (Newline Delimited JSON) — 适合 BI 引擎 streaming.

    每行一个 JSON 对象, 支持 JSON streaming 解析.
    """
    if dataset == BIDatasetKey.AUDIT_EVENTS:
        stmt = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
        if since:
            stmt = stmt.where(AuditEvent.occurred_at >= since)
        if until:
            stmt = stmt.where(AuditEvent.occurred_at <= until)
        stmt = stmt.order_by(AuditEvent.occurred_at.desc()).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        for r in rows:
            yield (
                json.dumps(
                    {
                        "event_id": str(r.event_id),
                        "tenant_id": str(r.tenant_id),
                        "user_id": str(r.user_id) if r.user_id else None,
                        "action": r.action,
                        "resource_type": r.resource_type,
                        "resource_id": str(r.resource_id) if r.resource_id else None,
                        "ip_address": r.ip_address,
                        "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8")

    elif dataset == BIDatasetKey.RUNS:
        stmt = select(Run).where(Run.tenant_id == tenant_id)
        if since:
            stmt = stmt.where(Run.created_at >= since)
        if until:
            stmt = stmt.where(Run.created_at <= until)
        stmt = stmt.order_by(Run.created_at.desc()).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        for r in rows:
            duration = (
                (r.finished_at - r.started_at).total_seconds() * 1000
                if r.started_at and r.finished_at
                else 0
            )
            yield (
                json.dumps(
                    {
                        "run_id": str(r.run_id),
                        "workflow_id": str(r.workflow_id),
                        "run_number": r.run_number,
                        "status": r.status,
                        "duration_ms": int(duration),
                        "started_at": r.started_at.isoformat() if r.started_at else None,
                        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8")
    else:
        yield b""


def render_dataset_parquet(
    rows: list[dict[str, Any]],
    columns: list[str],
) -> bytes:
    """生成 Parquet 字节流 (依赖 pandas + pyarrow, 缺失则抛 ImportError).

    Args:
        rows: 行数据列表 (dict).
        columns: 列顺序.

    Returns:
        Parquet 文件二进制内容.
    """
    try:
        import pandas as pd

        df = pd.DataFrame(rows, columns=columns)
        buf = io.BytesIO()
        df.to_parquet(buf, engine="pyarrow", index=False)
        return buf.getvalue()
    except ImportError as e:
        msg = "Parquet 导出需要 pandas + pyarrow 依赖"
        raise ImportError(msg) from e


# ===== BI 工具连接模板 =====


def generate_powerbi_template(
    *,
    tenant_id: UUID,
    tenant_slug: str,
    base_url: str,
) -> dict[str, Any]:
    """生成 PowerBI 直连模板 (Phase 7 B33 验收).

    PowerBI 可通过 Web API 连接器直接消费 HSCredit 的流式 API.
    返回 JSON 模板, 包含 M 查询和导入说明.
    """
    base = base_url.rstrip("/")
    queries = [
        PowerBIQueryInfo(
            name="audit_events",
            display_name="审计事件",
            description="租户级审计事件流",
            m_query=(
                f'let\n'
                f'    Source = Json.Document(Web.Contents("{base}/api/v1/{tenant_slug}/bi-exports/stream/audit_events", '
                f'[Headers=[#"Authorization"="Bearer " & Token]])),\n'
                f'    Lines = Lines.FromText(Source),\n'
                f'    AsTable = Table.FromList(Lines, Splitter.SplitByNothing(), {"{"}"raw"{"}"})\n'
                f'in\n'
                f'    AsTable'
            ),
        ),
        PowerBIQueryInfo(
            name="runs",
            display_name="工作流运行",
            description="Run 执行记录 (含耗时/状态)",
            m_query=(
                f'let\n'
                f'    Url = "{base}/api/v1/{tenant_slug}/bi-exports/stream/runs",\n'
                f'    Response = Web.Contents(Url, [Headers=[#"Authorization"="Bearer " & Token]]),\n'
                f'    Lines = Lines.FromBinary(Response, null, null, 65001),\n'
                f'    AsTable = Table.FromList(Lines, Splitter.SplitByNothing(), {"{"}"raw"{"}"})\n'
                f'in\n'
                f'    AsTable'
            ),
        ),
        PowerBIQueryInfo(
            name="billing",
            display_name="账单",
            description="租户账单",
            m_query=(
                f'let\n'
                f'    Url = "{base}/api/v1/{tenant_slug}/bi-exports/stream/billing",\n'
                f'    Response = Web.Contents(Url, [Headers=[#"Authorization"="Bearer " & Token]])\n'
                f'in\n'
                f'    Csv.Document(Response, [Delimiter=",", Encoding=65001])'
            ),
        ),
    ]

    return {
        "tenant_id": str(tenant_id),
        "tenant_slug": tenant_slug,
        "base_url": base,
        "protocol": "https",
        "auth_method": "bearer_token",
        "queries": [q.model_dump() for q in queries],
        "import_instructions": (
            "1. 在 PowerBI Desktop 中选择 Get Data → Web\\n"
            "2. 选择 Advanced Editor\\n"
            "3. 粘贴上方 M Query 替换示例 URL\\n"
            "4. 在 Token 参数中填入租户管理员 JWT token\\n"
            "5. 加载后可设置 Refresh Schedule 定时刷新"
        ),
        "raw_config": {
            "DataSourceKind": "Web",
            "DataSourcePath": base,
            "Timeout": 300,
            "BatchSize": 10000,
        },
    }


def generate_tableau_template(
    *,
    tenant_id: UUID,
    tenant_slug: str,
    connection: TableauConnectionInfo | None = None,
) -> dict[str, Any]:
    """生成 Tableau .tds 模板 (Phase 7 B33 验收).

    Tableau 通过 PostgreSQL ODBC 直接连接平台数据库,
    或通过 Web Data Connector (WDC) 调用 streaming API.
    """
    if connection is None:
        connection = TableauConnectionInfo(
            server="localhost",
            port=5432,
            database="hscredit",
            username="bi_reader",
        )

    # Tableau .tds 简化 XML 结构
    schema_xml = f"""<?xml version='1.0' encoding='utf-8' ?>
<datasource formatted-name='HSCredit-{tenant_slug}' inline='true' version='18.1'>
  <connection class='postgres' dbname='{connection.database}' port='{connection.port}' server='{connection.server}' sslmode='require' username='{connection.username}'>
    <relation name='v_bi_audit_recent' table='[v_bi_audit_recent]' type='table'>
      <columns>
        <column datatype='uuid' name='event_id'/>
        <column datatype='uuid' name='tenant_id'/>
        <column datatype='string' name='action'/>
        <column datatype='string' name='resource_type'/>
        <column datatype='datetime' name='occurred_at'/>
      </columns>
    </relation>
    <relation name='v_bi_run_summary' table='[v_bi_run_summary]' type='table'>
      <columns>
        <column datatype='uuid' name='run_id'/>
        <column datatype='string' name='status'/>
        <column datatype='int' name='duration_ms'/>
        <column datatype='datetime' name='started_at'/>
      </columns>
    </relation>
    <relation name='v_bi_billing_summary' table='[v_bi_billing_summary]' type='table'>
      <columns>
        <column datatype='uuid' name='bill_id'/>
        <column datatype='string' name='billing_period'/>
        <column datatype='real' name='total_amount'/>
        <column datatype='string' name='currency'/>
      </columns>
    </relation>
  </connection>
</datasource>"""

    return {
        "tenant_id": str(tenant_id),
        "tenant_slug": tenant_slug,
        "connection": {
            "server": connection.server,
            "port": connection.port,
            "database": connection.database,
            "username": connection.username,
            "use_ssl": connection.use_ssl,
        },
        "schema_xml": schema_xml,
        "import_instructions": (
            f"1. 保存上方 schema_xml 为 HSCredit-{tenant_slug}.tds\n"
            "2. Tableau Desktop → Connect → To a Server → PostgreSQL\n"
            "3. 填入 Server / Port / Database / Username / Password\n"
            "4. 选择 New Custom SQL 或直接拖入视图 v_bi_*\n"
            "5. publish to Tableau Server 即可定时刷新"
        ),
    }


def generate_finebi_template(
    *,
    tenant_id: UUID,
    tenant_slug: str,
) -> dict[str, Any]:
    """生成帆软 FineBI 数据包模板 (Phase 7 B33 验收 - 中文客户).

    FineBI 是国内主流 BI 工具, 通过 SQL 抽取或 API 拉取数据.
    返回结构含中文表名 + 抽取 SQL + FineBI 数据包配置 XML.
    """
    tables = [
        FineBITableInfo(
            table_name="bi_audit_events",
            display_name="审计事件",
            description="审计事件流 (含敏感字段访问/权限变更)",
            sql=(
                "SELECT event_id, tenant_id, user_id, action, resource_type, "
                "resource_id, ip_address, occurred_at FROM audit_events "
                "WHERE tenant_id = :tenant_id ORDER BY occurred_at DESC"
            ),
            fields=["event_id", "tenant_id", "user_id", "action", "resource_type", "occurred_at"],
        ),
        FineBITableInfo(
            table_name="bi_runs",
            display_name="工作流运行",
            description="Run 执行记录 (用于性能/失败分析)",
            sql=(
                "SELECT run_id, workflow_id, run_number, status, started_at, "
                "finished_at, "
                "EXTRACT(EPOCH FROM (finished_at - started_at)) * 1000 AS duration_ms "
                "FROM runs WHERE tenant_id = :tenant_id ORDER BY created_at DESC"
            ),
            fields=["run_id", "workflow_id", "run_number", "status", "duration_ms"],
        ),
        FineBITableInfo(
            table_name="bi_billing",
            display_name="账单",
            description="租户账单 (含基础费+超量费)",
            sql=(
                "SELECT bill_id, billing_period, plan, status, base_fee, "
                "overage_runs_fee, overage_duration_fee, overage_storage_fee, "
                "total_amount, currency, due_date FROM bills "
                "WHERE tenant_id = :tenant_id ORDER BY billing_period DESC"
            ),
            fields=["bill_id", "billing_period", "plan", "status", "total_amount", "currency"],
        ),
    ]

    config_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<BI-Package>
  <name>HSCredit 数据包 - {tenant_slug}</name>
  <description>HSCredit Studio BI 数据集 ({tenant_id})</description>
  <datasource type="jdbc">
    <driver>org.postgresql.Driver</driver>
    <url>jdbc:postgresql://${{DB_HOST}}:5432/hscredit</url>
    <user>${{DB_USER}}</user>
    <password>${{DB_PASSWORD}}</password>
  </datasource>
  <tables>
    <table name="bi_audit_events" display="审计事件" schema="bi"/>
    <table name="bi_runs" display="工作流运行" schema="bi"/>
    <table name="bi_billing" display="账单" schema="bi"/>
  </tables>
  <refresh-schedule>
    <interval>hourly</interval>
  </refresh-schedule>
</BI-Package>"""

    return {
        "tenant_id": str(tenant_id),
        "tenant_slug": tenant_slug,
        "display_name_zh": f"HSCredit 数据包 - {tenant_slug}",
        "display_name_en": f"HSCredit Package - {tenant_slug}",
        "tables": [t.model_dump() for t in tables],
        "config_xml": config_xml,
        "import_instructions_zh": (
            "1. 登录 FineBI 控制台 → 数据准备 → 数据包管理\n"
            "2. 选择导入数据包 → 上方 config_xml 另存为 .xml\n"
            "3. 编辑数据库连接: 替换 ${{DB_HOST}} / ${{DB_USER}} / ${{DB_PASSWORD}} 为实际值\n"
            "4. 导入后系统自动抽取 3 张表\n"
            "5. 在仪表板中使用抽取后的表进行可视化\n"
            "6. 可配置定时刷新 (默认每小时)"
        ),
    }


# ===== BI 数据库视图清单 =====


async def list_bi_views(session: AsyncSession) -> list[BIViewInfo]:
    """列出 BI 专用数据库视图 (Phase 7 B33).

    视图由 alembic 0012_bi_views 迁移创建.
    """
    # 查询 v_bi_* 视图
    stmt = text(
        """
        SELECT table_schema, table_name
        FROM information_schema.views
        WHERE table_name LIKE 'v_bi_%'
        ORDER BY table_name
        """
    )
    rows = (await session.execute(stmt)).all()

    descriptions = {
        "v_bi_audit_recent": "近 90 天审计事件 (扁平化 JSONB 详情)",
        "v_bi_run_summary": "Run 汇总 (按 workflow 聚合耗时/成功率)",
        "v_bi_usage_daily": "用量按日聚合 (Run/Sandbox/Storage)",
        "v_bi_billing_summary": "账单汇总 (含税/超量明细)",
    }

    result: list[BIViewInfo] = []
    for schema, name in rows:
        # 查询列
        col_stmt = text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :name
            ORDER BY ordinal_position
            """
        )
        cols = (await session.execute(col_stmt, {"schema": schema, "name": name})).scalars().all()
        result.append(
            BIViewInfo(
                name=name,
                **{"schema": schema},
                description=descriptions.get(name, ""),
                columns=list(cols),
            )
        )
    return result


__all__ = [
    "DATASETS",
    "BIDatasetKey",
    "DatasetSpec",
    "generate_finebi_template",
    "generate_powerbi_template",
    "generate_tableau_template",
    "iter_dataset_csv",
    "iter_dataset_json",
    "list_bi_views",
    "list_datasets",
    "render_dataset_parquet",
]
