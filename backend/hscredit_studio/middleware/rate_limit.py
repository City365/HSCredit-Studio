"""租户级速率限制中间件.

策略:
- 基于 Redis 滑动窗口 (sliding window log algorithm)
- 按 (tenant_slug, user_id) 维度独立计数
- 超限返回 429 Too Many Requests + Retry-After 头
- 公开路径 (/api/v1/auth/login, /api/v1/healthz, /metrics, /ws) 不受限

Phase 2 批次 13 — 防止租户恶意刷接口,保护后端 + 数据库.
"""
from __future__ import annotations

import time
from typing import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from hscredit_studio.core.config import settings
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
    """基于 Redis 滑动窗口的租户级速率限制.

    算法: sliding window counter (精度 1 秒,无 burst)
    - key: ``rl:{tenant_slug}:{user_id_or_ip}``
    - value: 滑动窗口内的请求时间戳列表
    - limit: settings.rate_limit_per_tenant (默认 100 / 60s)
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
            except Exception:
                pass

        # 也支持 IP 兜底
        client_ip = request.client.host if request.client else "unknown"

        key = f"rl:{tenant_slug}:{user_id}"
        limit = settings.rate_limit_per_tenant
        window = settings.rate_limit_window_seconds

        allowed, retry_after = await self._check(key, limit, window)
        if not allowed:
            _log.warning(
                "rate_limit_exceeded",
                extra={"tenant": tenant_slug, "user": user_id, "ip": client_ip, "path": path},
            )
            resp = JSONResponse(
                status_code=429,
                content={
                    "code": "E_RATE_LIMITED",
                    "message": f"超出速率限制 ({limit} 请求 / {window}s), 请稍后重试",
                    "details": {"retry_after_seconds": retry_after},
                },
            )
            resp.headers["Retry-After"] = str(retry_after)
            resp.headers["X-RateLimit-Limit"] = str(limit)
            resp.headers["X-RateLimit-Remaining"] = "0"
            return resp

        response = await call_next(request)
        # 写入 rate limit 头 (供前端展示)
        response.headers["X-RateLimit-Limit"] = str(limit)
        return response

    async def _check(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        """检查是否超出限速,使用 Redis sorted set 实现滑动窗口.

        Returns:
            (allowed, retry_after_seconds)
        """
        try:
            from hscredit_studio.services.cache import get_cache_client

            client = await get_cache_client()
            now = time.time()
            cutoff = now - window

            # 1. 删除窗口外的旧记录
            await client.zremrangebyscore(key, 0, cutoff)
            # 2. 计数当前窗口
            count = await client.zcard(key)
            if count >= limit:
                # 计算最早一个时间戳, 距窗口起点多久
                earliest = await client.zrange(key, 0, 0, withscores=True)
                if earliest:
                    ts = earliest[0][1]
                    retry_after = max(1, int(window - (now - ts)) + 1)
                else:
                    retry_after = window
                return False, retry_after

            # 3. 记录当前请求 (member 必须唯一, 用时间戳+随机数避免冲突)
            import secrets
            member = f"{now}:{secrets.token_hex(4)}"
            await client.zadd(key, {member: now})
            # 4. 设置 key 过期 (比窗口稍长避免内存泄漏)
            await client.expire(key, window + 60)
            return True, 0
        except Exception as e:
            # Redis 失败时放行 (fail-open), 仅 WARN
            _log.warning("rate_limit_check_failed", extra={"key": key, "error": str(e)[:200]})
            return True, 0


__all__ = ["RateLimitMiddleware"]