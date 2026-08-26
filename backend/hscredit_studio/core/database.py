"""数据库连接与会话管理."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from hscredit_studio.core.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy 声明基类."""
    pass


# 异步引擎
#
# pool_pre_ping=False：Windows 上 asyncpg 在 Celery solo worker 模式下
# 会触发 MissingGreenlet（pre-ping 走 sync API 与 asyncpg greenlet 冲突）。
# NullPool：每次用完即关闭连接，避免连接复用时的 ping 问题；
# 对于 Celery 短生命周期任务 + FastAPI 请求都适用（牺牲一点连接开销换稳定）。
engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
    echo=settings.database_echo,
)

# 异步 Session 工厂
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI 依赖：获取数据库会话."""
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession]:
    """用于非 FastAPI 场景的会话上下文."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def set_tenant_context(session: AsyncSession, tenant_id: str) -> None:
    """设置 RLS 上下文（用于多租户隔离）.

    注意：SET LOCAL 不支持参数化绑定（asyncpg 限制），
    必须用 str() 转义后直接拼接到 SQL 中。tenant_id 是我们自己的 UUID 输入，
    不会包含引号或分号，所以 f-string 安全。
    """
    safe_tid = str(tenant_id).replace("'", "")
    await session.execute(text(f"SET LOCAL app.current_tenant = '{safe_tid}'"))


from sqlalchemy import text  # noqa: E402
