"""Alembic 环境配置（异步 SQLAlchemy 2.0）.

要点：

1. 通过 settings.database_url 动态注入连接串，避免硬编码。
2. 在线模式使用 ``async_engine_from_config`` + ``asyncio.run``。
3. 离线模式只生成 SQL（``--sql`` 用法）。
4. 所有 model 通过 ``from hscredit_studio.models import *`` 注册到 ``Base.metadata``，
   保证 ``autogenerate`` 能检测到完整 schema。
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ---- 应用配置 / 元数据注入 ----
from hscredit_studio.core.config import settings
from hscredit_studio.core.database import Base

# 注册所有 ORM model；不可移除，否则 autogenerate 将看不到任何表
from hscredit_studio.models import *  # noqa: E402, F401, F403


config = context.config

# 用 settings.database_url 覆盖 alembic.ini 中的 sqlalchemy.url
config.set_main_option("sqlalchemy.url", settings.database_url)

# 配置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 元数据：autogenerate 据此比对模型与数据库差异
target_metadata = Base.metadata


# ===== 离线模式（生成 SQL 脚本，不连接数据库） =====


def run_migrations_offline() -> None:
    """以离线模式运行迁移.

    通过 ``alembic upgrade head --sql`` 等方式输出 SQL，
    无需建立数据库连接。常用于审查/审计场景。
    """
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("sqlalchemy.url 未配置，请检查 alembic.ini 或 Settings.database_url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ===== 在线模式：同步入口，由 do_run_migrations 包装真正的迁移逻辑 =====


def do_run_migrations(connection: Connection) -> None:
    """在同步 Connection 上执行迁移（被 run_async_migrations 调用）."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
        # render_as_batch=False  # PG 通常不需要
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """使用 async engine 注入连接池并运行迁移."""
    connectable_config: dict[str, Any] = config.get_section(config.config_ini_section, {})
    if not connectable_config.get("sqlalchemy.url"):
        raise RuntimeError("sqlalchemy.url 未配置")

    connectable = async_engine_from_config(
        connectable_config,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """在线模式入口：套上 asyncio 事件循环."""
    asyncio.run(run_async_migrations())


# ---- 入口分发 ----
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
