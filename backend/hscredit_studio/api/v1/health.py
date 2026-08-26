"""健康检查端点."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from hscredit_studio.core.database import async_session_maker
from hscredit_studio.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/healthz", summary="存活检查")
async def healthz() -> dict:
    """存活探针（K8s livenessProbe）."""
    return {"status": "ok"}


@router.get("/readyz", summary="就绪检查")
async def readyz() -> dict:
    """就绪探针（K8s readinessProbe）."""
    checks = {
        "database": await check_database(),
        # "redis": await check_redis(),
        # "minio": await check_minio(),
    }
    if all(checks.values()):
        return {"status": "ready", "checks": checks}
    raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})


async def check_database() -> bool:
    """检查数据库连接."""
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database check failed: {e}")
        return False
