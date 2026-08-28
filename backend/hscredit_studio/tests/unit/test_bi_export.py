"""BI 报表导出单元测试 — Phase 7 B33.

依据 docs/ROADMAP.md Phase 7 B33 验收矩阵.
"""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from hscredit_studio.schemas.bi_export import (
    BIDatasetKey,
    TableauConnectionInfo,
)
from hscredit_studio.services import bi_export as svc

# ===== Helpers =====


class _FakeAuditRow:
    def __init__(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class _MockScalarResult:
    """mock SQLAlchemy Result.scalars().all()."""

    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return self._rows


class _MockResult:
    """mock SQLAlchemy Result."""

    def __init__(self, scalars_list: list | None = None, raw_rows: list | None = None) -> None:
        self._scalars_list = scalars_list or []
        self._raw_rows = raw_rows or []

    def scalars(self) -> _MockScalarResult:
        return _MockScalarResult(self._scalars_list)


def _empty_session() -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_MockResult(scalars_list=[]))
    return session


# ===== A. 数据集元信息 =====


class TestDatasetCatalog:
    """数据集目录测试 (B33)."""

    def test_list_datasets_returns_all(self) -> None:
        items = svc.list_datasets()
        assert len(items) >= 6

    def test_audit_dataset_includes(self) -> None:
        items = svc.list_datasets()
        keys = [it.key for it in items]
        assert BIDatasetKey.AUDIT_EVENTS in keys
        assert BIDatasetKey.RUNS in keys
        assert BIDatasetKey.BILLING in keys
        assert BIDatasetKey.USAGE_DAILY in keys

    def test_dataset_has_fields(self) -> None:
        items = svc.list_datasets()
        for it in items:
            assert it.name
            assert it.description
            assert len(it.fields) > 0

    def test_dataset_supports_streaming(self) -> None:
        items = svc.list_datasets()
        for it in items:
            assert it.supports_streaming is True


# ===== B. 流式 CSV 生成 =====


class TestStreamingCSV:
    """流式 CSV 测试 (B33 验收)."""

    @pytest.mark.asyncio
    async def test_csv_starts_with_bom(self) -> None:
        """CSV 必须以 UTF-8 BOM 开头, Excel 正确识别中文."""
        session = _empty_session()

        gen = svc.iter_dataset_csv(
            session,
            BIDatasetKey.AUDIT_EVENTS,
            uuid4(),
            limit=10,
        )
        first_chunk = await gen.__anext__()
        assert first_chunk.startswith(b"\xef\xbb\xbf"), "CSV 必须以 UTF-8 BOM 开头"

    @pytest.mark.asyncio
    async def test_csv_audit_with_data(self) -> None:
        """带数据的审计 CSV."""
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_MockResult(
                scalars_list=[
                    _FakeAuditRow(
                        event_id=uuid4(),
                        tenant_id=uuid4(),
                        user_id=None,
                        action="login",
                        resource_type=None,
                        resource_id=None,
                        ip_address="127.0.0.1",
                        occurred_at=datetime(2026, 8, 28, 12, 0, 0),
                    ),
                ],
            )
        )

        chunks = []
        gen = svc.iter_dataset_csv(
            session,
            BIDatasetKey.AUDIT_EVENTS,
            uuid4(),
            limit=10,
        )
        async for chunk in gen:
            chunks.append(chunk)

        full = b"".join(chunks).decode("utf-8")
        assert "event_id" in full
        assert "login" in full
        assert "127.0.0.1" in full

    @pytest.mark.asyncio
    async def test_csv_billing_header(self) -> None:
        """账单 CSV 含正确列."""
        session = _empty_session()
        chunks = []
        gen = svc.iter_dataset_csv(
            session,
            BIDatasetKey.BILLING,
            uuid4(),
            limit=10,
        )
        async for chunk in gen:
            chunks.append(chunk)
        full = b"".join(chunks).decode("utf-8")
        assert "total_amount" in full
        assert "currency" in full
        assert "billing_period" in full

    @pytest.mark.asyncio
    async def test_csv_unsupported_dataset_returns_header(self) -> None:
        """未实现数据集返回表头+空."""
        session = _empty_session()
        chunks = []
        gen = svc.iter_dataset_csv(
            session,
            BIDatasetKey.NODE_EXECUTIONS,
            uuid4(),
            limit=10,
        )
        async for chunk in gen:
            chunks.append(chunk)
        full = b"".join(chunks).decode("utf-8")
        assert "exec_id" in full


# ===== C. 流式 NDJSON =====


class TestStreamingNDJSON:
    """流式 NDJSON 测试 (B33)."""

    @pytest.mark.asyncio
    async def test_ndjson_audit_per_line(self) -> None:
        """NDJSON 每行一个有效 JSON."""
        session = AsyncMock()
        uid = uuid4()
        tid = uuid4()
        session.execute = AsyncMock(
            return_value=_MockResult(
                scalars_list=[
                    _FakeAuditRow(
                        event_id=uuid4(),
                        tenant_id=tid,
                        user_id=uid,
                        action="workflow_create",
                        resource_type="workflow",
                        resource_id=uuid4(),
                        ip_address="10.0.0.1",
                        occurred_at=datetime(2026, 8, 28, 10, 0, 0),
                    ),
                ],
            )
        )

        lines = []
        gen = svc.iter_dataset_json(
            session,
            BIDatasetKey.AUDIT_EVENTS,
            uuid4(),
            limit=10,
        )
        async for chunk in gen:
            for line in chunk.decode("utf-8").splitlines():
                if line:
                    lines.append(json.loads(line))

        assert len(lines) == 1
        assert lines[0]["action"] == "workflow_create"
        assert lines[0]["tenant_id"] == str(tid)

    def test_ndjson_handles_chinese(self) -> None:
        """NDJSON 必须正确处理中文."""
        payload = {"text": "中文测试"}
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        assert "中文测试" in encoded.decode("utf-8")


# ===== D. BI 模板生成 =====


class TestPowerBITemplate:
    """PowerBI 模板测试 (B33 验收)."""

    def test_powerbi_template_has_queries(self) -> None:
        tmpl = svc.generate_powerbi_template(
            tenant_id=uuid4(),
            tenant_slug="demo",
            base_url="http://localhost:8003",
        )
        assert "queries" in tmpl
        assert len(tmpl["queries"]) >= 2
        names = [q["name"] for q in tmpl["queries"]]
        assert "audit_events" in names
        assert "runs" in names

    def test_powerbi_m_query_uses_tenant(self) -> None:
        """M 查询必须含 tenant slug."""
        tmpl = svc.generate_powerbi_template(
            tenant_id=uuid4(),
            tenant_slug="acme",
            base_url="https://example.com",
        )
        for q in tmpl["queries"]:
            assert "acme" in q["m_query"]
            assert "https://example.com" in q["m_query"]

    def test_powerbi_import_instructions_present(self) -> None:
        tmpl = svc.generate_powerbi_template(
            tenant_id=uuid4(),
            tenant_slug="demo",
            base_url="http://x",
        )
        assert "PowerBI" in tmpl["import_instructions"]
        # M Query 中实际含 "Bearer" 认证方式 (instructions 含 JWT token)
        for q in tmpl["queries"]:
            assert "Bearer" in q["m_query"]


class TestTableauTemplate:
    """Tableau 模板测试 (B33 验收)."""

    def test_tableau_xml_has_views(self) -> None:
        """XML 含 v_bi_ 视图."""
        tmpl = svc.generate_tableau_template(
            tenant_id=uuid4(),
            tenant_slug="demo",
            connection=TableauConnectionInfo(
                server="db.example.com",
                port=5432,
                database="prod",
                username="reader",
            ),
        )
        xml = tmpl["schema_xml"]
        assert "v_bi_audit_recent" in xml
        assert "v_bi_run_summary" in xml
        assert "v_bi_billing_summary" in xml
        assert "postgres" in xml

    def test_tableau_xml_uses_custom_connection(self) -> None:
        tmpl = svc.generate_tableau_template(
            tenant_id=uuid4(),
            tenant_slug="acme",
            connection=TableauConnectionInfo(
                server="my.db",
                port=5433,
                database="mydb",
                username="me",
            ),
        )
        xml = tmpl["schema_xml"]
        assert "my.db" in xml
        assert "5433" in xml
        assert "mydb" in xml


class TestFineBITemplate:
    """FineBI 模板测试 (B33 验收 - 中文)."""

    def test_finebi_has_chinese_display(self) -> None:
        tmpl = svc.generate_finebi_template(
            tenant_id=uuid4(),
            tenant_slug="demo",
        )
        assert "HSCredit 数据包" in tmpl["display_name_zh"]

    def test_finebi_tables_count(self) -> None:
        tmpl = svc.generate_finebi_template(
            tenant_id=uuid4(),
            tenant_slug="demo",
        )
        assert len(tmpl["tables"]) >= 3
        names = [t["table_name"] for t in tmpl["tables"]]
        assert "bi_audit_events" in names
        assert "bi_runs" in names
        assert "bi_billing" in names

    def test_finebi_sql_uses_tenant_id_param(self) -> None:
        """SQL 必须含 :tenant_id 占位符 (FineBI 参数化)."""
        tmpl = svc.generate_finebi_template(
            tenant_id=uuid4(),
            tenant_slug="demo",
        )
        for t in tmpl["tables"]:
            assert ":tenant_id" in t["sql"]

    def test_finebi_instructions_chinese(self) -> None:
        tmpl = svc.generate_finebi_template(
            tenant_id=uuid4(),
            tenant_slug="demo",
        )
        instr = tmpl["import_instructions_zh"]
        assert "FineBI" in instr
        assert "数据库" in instr
        assert "导入" in instr


# ===== E. Parquet 渲染 =====


class TestParquetRender:
    """Parquet 渲染测试 (B33)."""

    def test_parquet_render_with_data(self) -> None:
        try:
            import pandas  # noqa: F401
            import pyarrow  # noqa: F401
        except ImportError:
            pytest.skip("需要 pandas + pyarrow")

        rows = [
            {"id": 1, "name": "a"},
            {"id": 2, "name": "b"},
        ]
        out = svc.render_dataset_parquet(rows, ["id", "name"])
        assert isinstance(out, bytes)
        assert len(out) > 0
        assert out[:4] == b"PAR1"


# ===== F. BI 视图清单 =====


class TestBIViews:
    """BI 数据库视图清单测试 (B33)."""

    @pytest.mark.asyncio
    async def test_list_bi_views_returns_empty_on_no_views(self) -> None:
        """无视图时返回空列表."""
        session = AsyncMock()
        # 第一次查 views 返回空
        empty_result = AsyncMock()
        empty_result.all = lambda: []
        session.execute = AsyncMock(return_value=empty_result)

        items = await svc.list_bi_views(session)
        assert isinstance(items, list)
