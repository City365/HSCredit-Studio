"""事件总线 — 通过 Redis pub/sub 解耦多 worker 推流.

Phase 1 用于 WebSocket 实时推流，Phase 2 可扩展到日志聚合 / 告警通知。
所有 publish 调用都是 fire-and-forget（不阻塞主流程），失败时仅记录 warn 日志。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis

from hscredit_studio.core.config import settings
from hscredit_studio.core.logging import get_logger

_log = get_logger(__name__)

# 单独的 redis 客户端（decode_responses=True 便于直接读 JSON 字符串）
_pub_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    """获取 pub/sub 专用 redis 客户端（lazy 单例）."""
    global _pub_redis
    if _pub_redis is None:
        _pub_redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _pub_redis


def _channel(run_id: UUID) -> str:
    return f"run:{run_id}"


def _now_ms() -> int:
    return int(time.time() * 1000)


async def publish_event(
    run_id: UUID,
    event_type: str,
    **payload: Any,
) -> None:
    """异步发布事件到 run:{run_id} channel（fire-and-forget）.

    Parameters
    ----------
    run_id:
        Run UUID。
    event_type:
        ``run_status`` / ``node_execution`` / ``log`` / ``ping`` 等。
    **payload:
        业务字段（如 ``node_id``, ``status``, ``message``, ``level``）。
    """
    event = {
        "type": event_type,
        "run_id": str(run_id),
        "ts": _now_ms(),
        **payload,
    }
    try:
        r = _get_redis()
        await r.publish(_channel(run_id), json.dumps(event, ensure_ascii=False, default=str))
    except Exception as e:
        # 推流失败不阻塞主流程
        _log.warning("publish_failed", event_type=event_type, run_id=str(run_id), error=str(e))


def publish_event_sync(
    run_id: UUID,
    event_type: str,
    **payload: Any,
) -> None:
    """同步 fire-and-forget 发布（用于非 async 上下文或最后兜底）.

    通过 asyncio.get_event_loop().create_task 启动协程；loop 不可用时退化为直接 await。
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            _task = loop.create_task(publish_event(run_id, event_type, **payload))  # noqa: RUF006
        else:
            loop.run_until_complete(publish_event(run_id, event_type, **payload))
    except RuntimeError:
        # 无事件循环（脚本退出时）：直接同步 await
        try:
            asyncio.run(publish_event(run_id, event_type, **payload))
        except Exception as e:
            _log.warning("publish_sync_failed", error=str(e))


__all__ = ["publish_event", "publish_event_sync"]
