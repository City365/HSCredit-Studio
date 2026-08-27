"""Rate Limiting 服务 — Phase 3 B15.

依据 docs/ROADMAP.md Phase 3 B15:

> Phase 2 B13 Rate Limiting 为进程内滑动窗口, 多副本部署后限流计数不共享。
> B15: 改为 Redis Lua 脚本原子 incr + expire, 多副本部署共享限流计数;
>      引入按租户分级限流策略 (free / pro / enterprise 三档)。

设计:

1. **算法**: sliding window log via Redis sorted set, 全部操作在 Lua 脚本内完成 (原子)。
2. **分级**: 根据 ``Tenant.plan`` 取不同 per_window 上限, plan 缓存在 Redis 60s。
3. **fail-open**: Redis 不可达时放行 (避免 Redis 故障让平台整体不可用), 仅 WARN 日志。
4. **公开路径**: 仍由 middleware 短路, 不进入本服务。

错误约定:

- :func:`check_rate_limit` 返回 :class:`RateLimitResult`。
- 超限时 ``allowed=False, retry_after>0``。
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any

from hscredit_studio.core.config import settings
from hscredit_studio.core.logging import get_logger

_log = get_logger(__name__)


# ===== 分级限流配置 =====

# 各 plan 默认限流额度 (per window)。可被环境变量覆盖。
_PLAN_LIMITS: dict[str, int] = {
    "free": 60,         # 60 req / 60s
    "pro": 300,          # 300 req / 60s
    "enterprise": 1200,  # 1200 req / 60s
}


# ===== Lua 脚本 =====

# KEYS[1] = rate limit key
# ARGV[1] = now (unix timestamp float)
# ARGV[2] = window seconds
# ARGV[3] = limit (max requests in window)
# ARGV[4] = unique member suffix (caller-supplied, e.g. token_hex(4))
#
# 1. 删除窗口外的旧记录 (ZREMRANGEBYSCORE)
# 2. 计数当前窗口 (ZCARD)
# 3. 若超限: 计算 retry_after (最早一条距窗口起点的差) 并返回 (0, retry_after, count)
# 4. 否则: ZADD 当前记录 + EXPIRE (原子)
# 5. 返回 (1, 0, count+1)
_LUA_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member_suffix = ARGV[4]

local cutoff = now - window
redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
local count = redis.call('ZCARD', key)

if count >= limit then
    local earliest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after
    if earliest[2] then
        local earliest_ts = tonumber(earliest[2])
        retry_after = math.ceil(window - (now - earliest_ts)) + 1
        if retry_after < 1 then retry_after = 1 end
    else
        retry_after = window
    end
    return {0, retry_after, count}
end

local member = tostring(now) .. ':' .. member_suffix
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window + 60)
return {1, 0, count + 1}
"""

# Lua 脚本 SHA 缓存 (避免每次请求都 SCRIPT LOAD)
_lua_sha_cache: str | None = None


@dataclass
class RateLimitResult:
    """Rate limit 检查结果."""

    allowed: bool
    retry_after_seconds: int
    limit: int
    current_count: int
    plan: str  # 用于响应头与日志


def get_plan_limit(plan: str) -> int:
    """根据租户 plan 取限流额度.

    优先级: 显式 plan 名 > 默认 ``free``。
    """
    return _PLAN_LIMITS.get(plan, _PLAN_LIMITS["free"])


async def _get_tenant_plan(tenant_slug: str) -> str:
    """查询租户 plan (Redis 缓存 60s, miss 则查 DB).

    Returns:
        plan 名称 (``free`` / ``pro`` / ``enterprise``)。
    """
    from hscredit_studio.services.cache import get_cache_client

    cache_key = f"tenant:plan:{tenant_slug}"
    try:
        client = await get_cache_client()
        cached = await client.get(cache_key)
        if isinstance(cached, bytes):
            cached = cached.decode("utf-8")
        if cached:
            return str(cached)
    except Exception as e:
        _log.debug("rate_limit_plan_cache_failed", slug=tenant_slug, error=str(e)[:200])

    # DB 查询 (限 middleware 调用, 60s 缓存避免热路径开销)
    from sqlalchemy import select

    from hscredit_studio.core.database import session_scope
    from hscredit_studio.models import Tenant

    try:
        async with session_scope() as session:
            row = await session.scalar(
                select(Tenant.plan).where(Tenant.slug == tenant_slug)
            )
            plan = row or "free"
    except Exception as e:
        _log.warning("rate_limit_plan_db_failed", slug=tenant_slug, error=str(e)[:200])
        return "free"

    # 回写缓存
    try:
        client = await get_cache_client()
        await client.set(cache_key, plan, ex=60)
    except Exception as e:
        _log.debug("rate_limit_plan_cache_write_failed", slug=tenant_slug, error=str(e)[:200])

    return plan


async def _load_lua_script(client: Any) -> str | None:
    """加载 Lua 脚本到 Redis 并缓存 SHA (协程, redis-py async 客户端需 await)."""
    global _lua_sha_cache
    try:
        _lua_sha_cache = await client.script_load(_LUA_SLIDING_WINDOW)
        return _lua_sha_cache
    except Exception as e:
        _log.debug("rate_limit_lua_load_failed", error=str(e)[:200])
        _lua_sha_cache = None
        return None


async def check_rate_limit(
    tenant_slug: str,
    user_id: str,
    *,
    client_ip: str | None = None,
) -> RateLimitResult:
    """检查 (tenant, user) 是否超出限速.

    Args:
        tenant_slug: 租户 slug (``global`` 表示未匹配租户, 用 free 额度)。
        user_id: 用户标识 (JWT sub 或 IP)。
        client_ip: 客户端 IP (备用, 当前未使用)。

    Returns:
        :class:`RateLimitResult`。
    """
    plan = await _get_tenant_plan(tenant_slug)
    limit = get_plan_limit(plan)
    window = settings.rate_limit_window_seconds
    key = f"rl:{tenant_slug}:{user_id}"

    try:
        from hscredit_studio.services.cache import get_cache_client

        client = await get_cache_client()
        member_suffix = secrets.token_hex(4)
        now = time.time()

        # 优先 EVALSHA (O(1) 调用), miss 时回退到 EVAL (脚本自动 LOAD)
        result: list[Any] | None = None
        if _lua_sha_cache:
            try:
                result = await client.evalsha(_lua_sha_cache, 1, key, str(now), str(window), str(limit), member_suffix)
            except Exception as e:
                _log.debug("rate_limit_evalsha_failed", error=str(e)[:200])
                # NOSCRIPT 时重载, 其他异常继续往下走 (走 EVAL)

        if result is None:
            # 尝试 SCRIPT LOAD + EVALSHA, 失败则 EVAL
            await _load_lua_script(client)
            if _lua_sha_cache:
                try:
                    result = await client.evalsha(_lua_sha_cache, 1, key, str(now), str(window), str(limit), member_suffix)
                except Exception:
                    result = None
            if result is None:
                result = await client.eval(_LUA_SLIDING_WINDOW, 1, key, str(now), str(window), str(limit), member_suffix)

        allowed_int, retry_after, current_count = int(result[0]), int(result[1]), int(result[2])
        return RateLimitResult(
            allowed=bool(allowed_int),
            retry_after_seconds=retry_after,
            limit=limit,
            current_count=current_count,
            plan=plan,
        )
    except Exception as e:
        # fail-open: Redis 故障放行, 仅 WARN
        _log.warning(
            "rate_limit_check_failed",
            extra={"key": key, "plan": plan, "error": str(e)[:200]},
        )
        return RateLimitResult(
            allowed=True,
            retry_after_seconds=0,
            limit=limit,
            current_count=0,
            plan=plan,
        )


def reset_rate_limit_cache() -> None:
    """重置 Lua SHA 缓存 (用于测试 / Redis 重启场景)."""
    global _lua_sha_cache
    _lua_sha_cache = None


__all__ = [
    "RateLimitResult",
    "check_rate_limit",
    "get_plan_limit",
    "reset_rate_limit_cache",
]
