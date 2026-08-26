"""安全响应头中间件 — 注入 OWASP 推荐的安全 HTTP 头.

实现要点：

- ``X-Content-Type-Options: nosniff`` — 禁止 MIME 嗅探。
- ``X-Frame-Options: DENY`` — 禁止 iframe 嵌入。
- ``X-XSS-Protection: 1; mode=block`` — 启用浏览器 XSS 过滤。
- ``Referrer-Policy: strict-origin-when-cross-origin`` — 限制 referrer 泄漏。
- ``Permissions-Policy`` — 关闭不常用硬件 API。
- ``Strict-Transport-Security`` — 仅 HTTPS 下注入（避免 HTTP 回退告警）。
- ``Content-Security-Policy`` — API 默认 ``default-src 'none'``，不渲染 HTML。
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 响应追加 OWASP 推荐的安全响应头."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # MIME 嗅探防护
        response.headers["X-Content-Type-Options"] = "nosniff"
        # 防止点击劫持
        response.headers["X-Frame-Options"] = "DENY"
        # 浏览器 XSS 过滤（兼容老浏览器）
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Referrer 限制
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # 关闭硬件 API（API 不需要）
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )

        # HSTS 仅在 HTTPS 下注入（HTTP 注入会被浏览器忽略且无意义）
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # CSP：API 不渲染 HTML，默认拒绝所有
        if request.url.path.startswith("/api/"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )

        return response