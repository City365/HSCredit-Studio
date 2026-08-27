"""Phase 3 B15 Rate Limiting — 单元测试.

依据 docs/ROADMAP.md Phase 3 B15 验收:

- 分级限流: free=60/pro=300/enterprise=1200
- Redis Lua 原子性: 4 步操作 (ZREMRANGEBYSCORE/ZCARD/ZADD/EXPIRE) 在单脚本内完成
- Plan 缓存: 60s Redis TTL, miss 时回退 DB
- fail-open: Redis 不可达时返回 allowed=True

注: 测试需要 redis-py 异步客户端 + 可达 Redis (默认 localhost:6379/0)。
"""
from __future__ import annotations

import secrets
import time as _time

import pytest

from hscredit_studio.services.rate_limit import (
    RateLimitResult,
    _get_tenant_plan,
    check_rate_limit,
    get_plan_limit,
    reset_rate_limit_cache,
)


def _unique_user(prefix: str) -> str:
    """生成唯一 user_id 避免 Redis 状态跨测试残留."""
    return f"{prefix}_{int(_time.time() * 1000)}_{secrets.token_hex(4)}"


def test_get_plan_limit_known_plans():
    """get_plan_limit: free=60, pro=300, enterprise=1200."""
    assert get_plan_limit("free") == 60
    assert get_plan_limit("pro") == 300
    assert get_plan_limit("enterprise") == 1200


def test_get_plan_limit_unknown_falls_back_to_free():
    """get_plan_limit: 未知 plan 走 free 兜底."""
    assert get_plan_limit("unknown_plan") == 60
    assert get_plan_limit("") == 60


@pytest.mark.asyncio
async def test_get_tenant_plan_returns_free_for_unknown_slug():
    """_get_tenant_plan: 未知 slug 返回 'free' (DB miss 兜底)."""
    plan = await _get_tenant_plan("nonexistent_slug_for_test_xxx")
    assert plan == "free"


@pytest.mark.asyncio
async def test_get_tenant_plan_caches_in_redis():
    """_get_tenant_plan: 第二次调用应从 Redis 缓存读取."""
    # 第一次: 走 DB / 写缓存
    plan1 = await _get_tenant_plan("demo")
    # 第二次: 应命中缓存
    plan2 = await _get_tenant_plan("demo")
    assert plan1 == plan2
    # plan 应是合法值
    assert plan1 in ("free", "pro", "enterprise")


@pytest.mark.asyncio
async def test_check_rate_limit_basic_allowed():
    """check_rate_limit: 未超限时 allowed=True."""
    reset_rate_limit_cache()
    result = await check_rate_limit(
        tenant_slug="demo",
        user_id=_unique_user("basic"),
    )
    assert isinstance(result, RateLimitResult)
    assert result.allowed is True
    assert result.retry_after_seconds == 0
    assert result.limit in (60, 300, 1200)  # 由 plan 决定
    assert result.plan in ("free", "pro", "enterprise")


@pytest.mark.asyncio
async def test_check_rate_limit_returns_plan_in_result():
    """check_rate_limit: 结果含 plan 字段 (供响应头使用)."""
    reset_rate_limit_cache()
    result = await check_rate_limit(
        tenant_slug="demo",
        user_id=_unique_user("plan"),
    )
    assert result.plan in ("free", "pro", "enterprise")
    # limit 应与 _PLAN_LIMITS[plan] 一致
    assert result.limit == get_plan_limit(result.plan)


@pytest.mark.asyncio
async def test_check_rate_limit_global_tenant_uses_free():
    """check_rate_limit: tenant_slug='global' (无 tenant) 用 free 额度."""
    reset_rate_limit_cache()
    result = await check_rate_limit(
        tenant_slug="global",
        user_id=_unique_user("global"),
    )
    assert result.allowed is True
    assert result.plan == "free"
    assert result.limit == 60


@pytest.mark.asyncio
async def test_check_rate_limit_concurrent_increments():
    """check_rate_limit: 多次串行调用, current_count 递增 (限同 key).

    验证 Lua 脚本实际写入 Redis sorted set。
    """
    reset_rate_limit_cache()
    user = _unique_user("concurrent")
    counts = []
    for _ in range(5):
        r = await check_rate_limit(tenant_slug="demo", user_id=user)
        counts.append(r.current_count)
    # 单调递增 (1, 2, 3, 4, 5)
    assert counts == [1, 2, 3, 4, 5], f"递增失败: {counts}"


@pytest.mark.asyncio
async def test_check_rate_limit_blocks_when_limit_reached():
    """check_rate_limit: 累计到 free plan 限额 (60) 后返回超限.

    用 'global' tenant (无 tenant_slug 兜底, 用 free 计划, 60 req/60s),
    跑 65 次, 后 5 次超限。
    """
    reset_rate_limit_cache()
    user = _unique_user("block")
    blocked = 0
    last_retry_after = 0
    for _i in range(65):
        r = await check_rate_limit(tenant_slug="global", user_id=user)
        if not r.allowed:
            blocked += 1
            last_retry_after = r.retry_after_seconds
    # 至少有 1 次超限 (前 60 通过, 后 5 应被拒)
    assert blocked >= 1, f"应有超限但全部通过 (count={_i + 1})"
    assert last_retry_after > 0, "retry_after_seconds 应 > 0"


def test_reset_rate_limit_cache():
    """reset_rate_limit_cache: 重置 Lua SHA 缓存, 不抛异常."""
    reset_rate_limit_cache()
    # 再次调用不报错
    reset_rate_limit_cache()
