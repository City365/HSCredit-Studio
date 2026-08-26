"""FastAPI 应用入口."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_client import make_asgi_app

from hscredit_studio.core.config import settings
from hscredit_studio.core.logging import setup_logging
from hscredit_studio.api.v1 import health
from hscredit_studio.api.v1 import auth, nodes, workflows, runs, templates, ws
from hscredit_studio.middleware.tenant import TenantMiddleware
from hscredit_studio.middleware.security import SecurityHeadersMiddleware
from hscredit_studio.middleware.request_id import RequestIDMiddleware

# 初始化日志
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期."""
    logger.info("🚀 HSCredit Workflow 启动中...")
    logger.info(f"   环境: {settings.environment}")
    logger.info(f"   调试: {settings.debug}")
    # 启动时初始化：数据库连接池、Redis、节点注册表等
    yield
    logger.info("👋 HSCredit Workflow 关闭中...")


# 创建 FastAPI 应用
app = FastAPI(
    title="HSCredit Workflow API",
    description="多租户 SaaS 建模工作台 API",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/v1/openapi.json",
)

# 中间件（顺序：最后添加的最先执行）
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TenantMiddleware)
app.add_middleware(RequestIDMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

# Prometheus 指标
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# 路由
app.include_router(health.router, prefix="/api/v1", tags=["健康检查"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["认证"])
app.include_router(workflows.router, prefix="/api/v1/{tenant_slug}/workflows", tags=["工作流"])
app.include_router(nodes.router, prefix="/api/v1/{tenant_slug}/node-definitions", tags=["节点定义"])
app.include_router(runs.router, prefix="/api/v1/{tenant_slug}/runs", tags=["运行"])
app.include_router(templates.router, prefix="/api/v1/{tenant_slug}/templates", tags=["模板"])
app.include_router(ws.router, prefix="/ws", tags=["WebSocket"])


@app.get("/")
async def root():
    """根端点."""
    return {
        "name": "HSCredit Workflow API",
        "version": app.version,
        "environment": settings.environment,
        "docs": "/api/docs",
    }
