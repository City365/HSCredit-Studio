"""FastAPI 应用入口."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_client import make_asgi_app

from hscredit_studio.api.exception_handlers import register_exception_handlers
from hscredit_studio.api.v1 import (
    admin,
    alerts,
    audit,
    auth,
    billing,
    contracts,
    data_classification,
    health,
    industry_templates,
    monitor,
    nodes,
    notifications,
    pipl,
    quota,
    rbac,
    runs,
    security,
    template_sharing,
    templates,
    usage,
    workflows,
    ws,
)
from hscredit_studio.core.config import settings
from hscredit_studio.core.logging import setup_logging
from hscredit_studio.middleware.rate_limit import RateLimitMiddleware
from hscredit_studio.middleware.request_id import RequestIDMiddleware
from hscredit_studio.middleware.security import SecurityHeadersMiddleware
from hscredit_studio.middleware.tenant import TenantMiddleware

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

# 注册全局异常处理
register_exception_handlers(app)

# 中间件（顺序：最后添加的最先执行）
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(RateLimitMiddleware)  # 速率限制 (越外层越先执行)
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
app.include_router(runs.router, prefix="/api/v1/{tenant_slug}/runs", tags=["运行"])
app.include_router(nodes.router, prefix="/api/v1/{tenant_slug}/node-definitions", tags=["节点定义"])
app.include_router(templates.router, prefix="/api/v1/{tenant_slug}/templates", tags=["模板"])
app.include_router(audit.router, prefix="/api/v1/{tenant_slug}/audit-events", tags=["审计"])
app.include_router(monitor.router, prefix="/api/v1/{tenant_slug}/monitor", tags=["监控"])
app.include_router(usage.router, prefix="/api/v1/{tenant_slug}/usage", tags=["用量"])
app.include_router(quota.router, prefix="/api/v1/{tenant_slug}/quota", tags=["配额"])
app.include_router(billing.router, prefix="/api/v1/{tenant_slug}/bills", tags=["账单"])
app.include_router(contracts.router, prefix="/api/v1/{tenant_slug}/contracts", tags=["合同"])
app.include_router(notifications.router, prefix="/api/v1/{tenant_slug}/notifications", tags=["通知"])
app.include_router(data_classification.router, prefix="/api/v1/{tenant_slug}/data-classification", tags=["数据脱敏"])
app.include_router(security.router, prefix="/api/v1/{tenant_slug}/security", tags=["安全加固"])
app.include_router(pipl.router, prefix="/api/v1/{tenant_slug}/pipl", tags=["PIPL"])
app.include_router(alerts.router, prefix="/api/v1/{tenant_slug}/alerts", tags=["告警"])
app.include_router(rbac.router, prefix="/api/v1/{tenant_slug}/rbac", tags=["RBAC"])
app.include_router(admin.router, prefix="/api/v1/{tenant_slug}/admin", tags=["超管后台"])
app.include_router(
    industry_templates.router,
    prefix="/api/v1/{tenant_slug}/industry-templates",
    tags=["行业模板"],
)
app.include_router(
    template_sharing.router,
    prefix="/api/v1/{tenant_slug}/template-sharing",
    tags=["模板共享"],
)
app.include_router(ws.router, prefix="/ws", tags=["WebSocket"])


# ===== 本地后备存储：直接下载端点（开发模式）=====
from pathlib import Path  # noqa: E402

from fastapi.responses import FileResponse  # noqa: E402

from hscredit_studio.services.storage import (  # noqa: E402
    _is_local_provider,
    _local_path,
)


@app.get("/api/v1/_storage/download", tags=["存储"], include_in_schema=False)
async def storage_download(bucket: str, key: str) -> FileResponse:
    """开发模式（STORAGE_PROVIDER=local）：直接通过后端路由下载对象.

    生产环境禁用——应通过 S3 预签名 URL 直连对象存储。
    """
    if not _is_local_provider():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="本地后备存储未启用")
    path = _local_path(bucket, key)
    if not path.exists():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="对象不存在")
    return FileResponse(path=str(path), filename=Path(key).name)


@app.get("/")
async def root():
    """根端点."""
    return {
        "name": "HSCredit Workflow API",
        "version": app.version,
        "environment": settings.environment,
        "docs": "/api/docs",
    }
