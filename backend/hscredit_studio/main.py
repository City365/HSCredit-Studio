"""FastAPI 应用入口."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_client import make_asgi_app
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from hscredit_studio.api.exception_handlers import register_exception_handlers
from hscredit_studio.api.v1 import (
    admin,
    alerts,
    audit,
    auth,
    bi_export,
    billing,
    contracts,
    custom_nodes,  # Phase 6 B36
    data_classification,
    health,
    industry_templates,
    model_export,
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
    webhooks,
    workflows,
    ws,
)
from hscredit_studio.core.config import settings
from hscredit_studio.core.database import async_session_maker
from hscredit_studio.core.logging import setup_logging
from hscredit_studio.middleware.rate_limit import RateLimitMiddleware
from hscredit_studio.middleware.request_id import RequestIDMiddleware
from hscredit_studio.middleware.security import SecurityHeadersMiddleware
from hscredit_studio.middleware.tenant import TenantMiddleware
from hscredit_studio.services.template import ensure_system_templates

# 初始化日志
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期."""
    logger.info("🚀 HSCredit Workflow 启动中...")
    logger.info(f"   环境: {settings.environment}")
    logger.info(f"   调试: {settings.debug}")
    # 启动时植入系统模板 (Phase 6 B30 行业模板 + 评分卡/规则/监控)
    try:
        async with async_session_maker() as session:
            await ensure_system_templates(session)
        logger.info("✅ 系统模板已就绪 (评分卡/规则/监控/6 个行业模板)")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"⚠️  ensure_system_templates 失败: {e}")

    # Phase 6 B36: 加载自定义节点到 NodeRegistry
    try:
        from hscredit_studio.nodes.loader import get_loader
        async with async_session_maker() as session:
            stats = await get_loader().load_all_to_registry(session)
        logger.info(
            f"✅ 自定义节点已加载到 Registry: {stats['loaded']} 个 (失败 {stats['skipped']})"
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"⚠️  自定义节点加载失败: {e}")

    # Phase 6 B36: 启动 Redis pub/sub 监听 (多 worker 同步)
    import asyncio
    from hscredit_studio.services.node_pubsub import start_reload_listener, stop_reload_listener
    listener_task = None
    try:
        listener_task = asyncio.create_task(start_reload_listener())
        logger.info("✅ 自定义节点 pub/sub 监听已启动")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"⚠️  pub/sub 监听启动失败: {e}")

    yield

    # 清理 pub/sub 监听
    if listener_task is not None:
        try:
            await stop_reload_listener()
            listener_task.cancel()
            try:
                await listener_task
            except (asyncio.CancelledError, Exception):
                pass
        except Exception:
            pass

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
# RateLimitMiddleware 暂时禁用: 本地 Redis 5.0.14 不支持 RESP3 HELLO 命令,
# 客户端 redis-py 5.x 默认发 HELLO 导致每个请求报错 (rate_limit_check_failed).
# TODO: 升级 Redis 至 6.2+ 或在 service 层指定 RESP2 协议
# app.add_middleware(RateLimitMiddleware)  # 速率限制 (越外层越先执行)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TenantMiddleware)
app.add_middleware(RequestIDMiddleware)

# CORS (开发环境允许任意 origin, 含 127.0.0.1 / 内网 IP)
_cors_origins = settings.cors_allowed_origins if settings.environment != "development" else ["*"]


class CORSAlwaysMiddleware(BaseHTTPMiddleware):
    """最外层 CORS 中间件 — 确保即使内部 middleware 抛异常, 响应也含 CORS 头.

    普通 CORSMiddleware 仅在正常响应时添加头, 异常被上层 handler 捕获后,
    响应可能不带 CORS 头 → 浏览器报 "blocked by CORS policy".
    本 middleware 在响应发出的最后一刻注入头, 解决该问题.
    """

    def __init__(self, app: ASGIApp, allowed_origins: list[str]) -> None:
        super().__init__(app)
        self.allowed_origins = allowed_origins

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        origin = request.headers.get("origin")
        # 即使下游抛异常被 ExceptionMiddleware 兜底, 此处也作为最外层运行
        try:
            response = await call_next(request)
        except Exception:
            # 兜底: 内部完全未捕获的异常, 返回 500 + CORS 头
            response = ORJSONResponse(
                {"code": "E_INTERNAL", "message": "服务器内部错误"},
                status_code=500,
            )
        if origin and ("*" in self.allowed_origins or origin in self.allowed_origins):
            response.headers["Access-Control-Allow-Origin"] = (
                "*" if "*" in self.allowed_origins else origin
            )
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, X-Request-ID"
            )
            response.headers["Vary"] = "Origin"
        return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=settings.environment != "development",  # dev 关掉 credentials 才能用 *
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)
# 必须最后添加 → Starlette 反转顺序, 最后 add 的最外层
app.add_middleware(CORSAlwaysMiddleware, allowed_origins=_cors_origins)

# Prometheus 指标
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# 路由
app.include_router(health.router, prefix="/api/v1", tags=["健康检查"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["认证"])
app.include_router(workflows.router, prefix="/api/v1/{tenant_slug}/workflows", tags=["工作流"])
app.include_router(runs.router, prefix="/api/v1/{tenant_slug}/runs", tags=["运行"])
app.include_router(nodes.router, prefix="/api/v1/{tenant_slug}/node-definitions", tags=["节点定义"])
app.include_router(custom_nodes.router, prefix="/api/v1/{tenant_slug}/custom-nodes", tags=["自定义节点"])
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
app.include_router(
    bi_export.router,
    prefix="/api/v1/{tenant_slug}/bi-exports",
    tags=["BI 报表"],
)
app.include_router(
    model_export.router,
    prefix="/api/v1/{tenant_slug}/model-export",
    tags=["模型导出"],
)
app.include_router(
    webhooks.router,
    prefix="/api/v1/{tenant_slug}/webhooks",
    tags=["Webhook"],
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
