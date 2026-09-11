"""数据源节点族 — 3 个数据库接入节点 (Phase 6 B36 阶段 3.2).

封装 hscredit.database 统一门面:

- ``database_mysql`` — MySQL 数据库
- ``database_postgres`` — PostgreSQL 数据库
- ``sql_query`` — 通用 SQL 查询 (根据 db_type 动态选择)

输入参数: host/port/db/user/password → 通过 Database 门面执行 SQL.
输出: ``df`` (DataFrame)
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hscredit_studio.core.exceptions import (
    DependencyError,
    ValidationError,
)
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.nodes.registry import register_node
from hscredit_studio.schemas.node_contract import (
    CacheConfig,
    NodeContract,
    ParamSpec,
    PortSchema,
)


def _build_db_contract(node_type: str, name: str, description: str, icon: str) -> NodeContract:
    return NodeContract(
        node_type=node_type,
        category="数据接入",
        name=name,
        description=description,
        icon=icon,
        inputs=[],
        outputs=[
            PortSchema(name="df", type="DataFrame", description="查询结果 DataFrame"),
        ],
        params=[
            ParamSpec(name="host", type="str", label="主机", required=True, placeholder="localhost"),
            ParamSpec(name="port", type="int", label="端口", default=3306, min=1, max=65535),
            ParamSpec(name="database", type="str", label="数据库名", required=True),
            ParamSpec(name="user", type="str", label="用户名", required=True),
            ParamSpec(name="password", type="str", label="密码", required=True),
            ParamSpec(name="sql", type="str", label="SQL 语句", required=True),
            ParamSpec(name="query_timeout", type="int", label="查询超时(秒)", default=60, min=1, max=3600, advanced=True),
        ],
        cache=CacheConfig(),
        timeout_sec=300,
        estimated_duration_sec=10,
        tags=["data_source", "database"],
        version="1.0.0",
    )


def _run_db_query(db_type: str, params: dict[str, Any], node_type: str) -> dict[str, Any]:
    """通用 DB 查询逻辑."""
    try:
        from hscredit.database import Database
    except ImportError as e:
        raise DependencyError(
            f"hscredit.database 不可用: {e}",
            details={"node_type": node_type, "package": "hscredit[db]"},
        ) from e

    sql = params.get("sql")
    if not sql or not sql.strip():
        raise ValidationError(
            "sql 参数不能为空",
            details={"node_type": node_type},
        )

    try:
        db = Database(
            database_type=db_type,
            host=params["host"],
            port=int(params.get("port", 3306 if db_type == "mysql" else 5432)),
            database=params["database"],
            user=params["user"],
            password=params["password"],
        )
        # 兼容 query 方法名: 优先 query, 回退到 read_sql / execute
        if hasattr(db, "query"):
            df = db.query(sql, timeout=int(params.get("query_timeout", 60)))
        elif hasattr(db, "read_sql"):
            df = db.read_sql(sql)
        elif hasattr(db, "execute"):
            df = db.execute(sql, return_type="dataframe")
        else:
            raise DependencyError(
                f"{db_type} Database 适配器无 query/read_sql/execute 方法",
                details={"node_type": node_type, "db_type": db_type},
            )
    except ValidationError:
        raise
    except Exception as e:
        raise DependencyError(
            f"{db_type} 查询失败: {e}",
            details={"node_type": node_type, "db_type": db_type, "sql_head": sql[:200]},
        ) from e

    if not isinstance(df, pd.DataFrame):
        try:
            df = pd.DataFrame(df)
        except Exception as e:
            raise ValidationError(
                f"查询结果无法转为 DataFrame: {e}",
                details={"node_type": node_type},
            ) from e

    return {"df": df}


# ===== 1. MySQL =====


@register_node
class DatabaseMySQLNode(BaseNode):
    contract = _build_db_contract(
        node_type="database_mysql",
        name="MySQL 数据库",
        description="从 MySQL 数据库查询数据 (返回 DataFrame)",
        icon="🐬",
    )

    def run(self, inputs, params):
        return _run_db_query("mysql", params, self.contract.node_type)


# ===== 2. PostgreSQL =====


@register_node
class DatabasePostgresNode(BaseNode):
    contract = _build_db_contract(
        node_type="database_postgres",
        name="PostgreSQL 数据库",
        description="从 PostgreSQL 数据库查询数据 (返回 DataFrame)",
        icon="🐘",
    )

    def run(self, inputs, params):
        return _run_db_query("postgres", params, self.contract.node_type)


# ===== 3. 通用 SQL 查询 (按 db_type 切换) =====


@register_node
class SQLQueryNode(BaseNode):
    """通用 SQL 查询 — db_type 动态选择适配器."""

    contract = NodeContract(
        node_type="sql_query",
        category="数据接入",
        name="SQL 查询",
        description="通用 SQL 查询节点 (支持 mysql/postgres/oracle/sqlserver/hive/clickhouse/...)",
        icon="📡",
        inputs=[],
        outputs=[PortSchema(name="df", type="DataFrame", description="查询结果 DataFrame")],
        params=[
            ParamSpec(name="db_type", type="str", label="数据库类型", required=True,
                      placeholder="mysql/postgres/oracle/..."),
            ParamSpec(name="host", type="str", label="主机", required=True, placeholder="localhost"),
            ParamSpec(name="port", type="int", label="端口", default=0,
                      description="0 表示按 db_type 使用默认端口"),
            ParamSpec(name="database", type="str", label="数据库名", required=True),
            ParamSpec(name="user", type="str", label="用户名", required=True),
            ParamSpec(name="password", type="str", label="密码", required=True),
            ParamSpec(name="sql", type="str", label="SQL 语句", required=True),
            ParamSpec(name="query_timeout", type="int", label="查询超时(秒)", default=60, min=1, max=3600, advanced=True),
        ],
        cache=CacheConfig(),
        timeout_sec=300,
        estimated_duration_sec=10,
        tags=["data_source", "sql"],
        version="1.0.0",
    )

    def run(self, inputs, params):
        db_type = params.get("db_type")
        if not db_type:
            raise ValidationError(
                "db_type 必填 (mysql/postgres/oracle/...)",
                details={"node_type": self.contract.node_type},
            )
        # port=0 → 用 db_type 默认端口
        if int(params.get("port", 0)) <= 0:
            default_ports = {
                "mysql": 3306, "postgres": 5432, "postgresql": 5432,
                "oracle": 1521, "sqlserver": 1433, "mssql": 1433,
                "hive": 10000, "clickhouse": 9000, "mongodb": 27017,
            }
            params = {**params, "port": default_ports.get(db_type.lower(), 0)}
        return _run_db_query(db_type.lower(), params, self.contract.node_type)