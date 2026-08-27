"""租户级速率限制中间件.

Phase 2 批次 13 (基础限速) + Phase 3 批次 15 (Redis Lua 原子化 + 分级限流).

策略:
- Redis 滑动窗口 log (sliding window log via sorted set, Lua 脚本原子执行)
- 按 (tenant_slug, user_id) 维度独立计数
- 超限返回 429 Too Many Requests + Retry-After 头
- 公开路径 (/api/v1/auth/login, /api/v1/healthz, /metrics, /ws) 不受限
- Phase 3 B15: 按 free/pro/enterprise 三档自动分配额度, 多副本共享 Redis 计数
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from hscredit_studio.core.logging import get_logger

_log = get_logger(__name__)


# 不受限的公开路径前缀
_PUBLIC_PATH_PREFIXES = (
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",
    "/api/v1/healthz",
    "/api/v1/openapi.json",
    "/api/v1/docs",
    "/api/v1/redoc",
    "/metrics",
    "/ws/",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """基于 Redis Lua 滑动窗口的租户级速率限制 (Phase 3 B15).

    算法: sliding window log via Redis sorted set, 全部 4 步操作在 1 个 Lua 脚本里完成,
    保证多 worker / 多副本部署下计数一致。

    分级: ``services.rate_limit.check_rate_limit`` 根据 ``Tenant.plan`` 取 ``free/pro/enterprise``
    档位, 限额 60/300/1200 req / 60s。
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        # 公开路径不限速
        if any(path.startswith(p) for p in _PUBLIC_PATH_PREFIXES):
            return await call_next(request)

        # 提取租户 / 用户标识
        tenant_slug = request.path_params.get("tenant_slug") or "global"
        user_id = request.headers.get("X-User-Id") or "anon"
        # 也从 JWT 提取 (Authorization: Bearer ...)
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            from hscredit_studio.core.security import decode_token

            try:
                payload = decode_token(auth.removeprefix("Bearer "))
                if "sub" in payload:
                    user_id = payload["sub"]
            except Exception as e:
                # JWT 无效时降级为 anon，避免阻塞正常流量；异常计入 debug 日志
                _log.debug("rate_limit_jwt_decode_failed", error=str(e))

        # 也支持 IP 兜底
        client_ip = request.client.host if request.client else "unknown"

        # Phase 3 B15: 调用 services.rate_limit.check_rate_limit (含 plan 查询 + Lua 原子执行)
        from hscredit_studio.services.rate_limit import check_rate_limit

        result = await check_rate_limit(
            tenant_slug=tenant_slug,
            user_id=user_id,
            client_ip=client_ip,
        )

        if not result.allowed:
            _log.warning(
                "rate_limit_exceeded",
                extra={
                    "tenant": tenant_slug,
                    "user": user_id,
                    "ip": client_ip,
                    "path": path,
                    "plan": result.plan,
                    "limit": result.limit,
                    "retry_after": result.retry_after_seconds,
                },
            )
            resp = JSONResponse(
                status_code=429,
                content={
                    "code": "E_RATE_LIMITED",
                    "message": (
                        f"超出速率限制 (plan={result.plan}, "
                        f"{result.limit} 请求 / 60s), 请稍后重试"
                    ),
                    "details": {"retry_after_seconds": result.retry_after_seconds},
                },
            )
            resp.headers["Retry-After"] = str(result.retry_after_seconds)
            resp.headers["X-RateLimit-Limit"] = str(result.limit)
            resp.headers["X-RateLimit-Remaining"] = "0"
            resp.headers["X-RateLimit-Plan"] = result.plan
            return resp

        response = await call_next(request)
        # 写入 rate limit 头 (供前端展示)
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Plan"] = result.plan
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, result.limit - result.current_count)
        )
        return response


__all__ = ["RateLimitMiddleware"]
