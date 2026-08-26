"""FastAPI 中间件集合.

按 main.py 注册顺序（最后添加的最先执行）：

- ``RequestIDMiddleware`` — 最先执行，生成 X-Request-ID
- ``TenantMiddleware`` — 校验 URL ``{tenant_slug}`` 与 JWT ``tenant_slug`` 一致
- ``SecurityHeadersMiddleware`` — 注入 OWASP 安全响应头
"""

from __future__ import annotations

from hscredit_studio.middleware.request_id import RequestIDMiddleware
from hscredit_studio.middleware.security import SecurityHeadersMiddleware
from hscredit_studio.middleware.tenant import TenantMiddleware

__all__ = [
    "RequestIDMiddleware",
    "SecurityHeadersMiddleware",
    "TenantMiddleware",
]