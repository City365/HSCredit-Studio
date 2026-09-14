"""自定义节点 pub/sub 同步服务 — Phase 6 B36.

设计 (依 docs/node-plugin/01_DESIGN.md 4.4 节):
- 当 custom_nodes 表有变化 (create/update_code/soft_delete) 时, 通过 Redis
  发布一条 reload 消息到 ``node:reload`` 频道
- 所有 worker 进程订阅此频道, 收到后从 DB 重新加载指定 node_type
- 这样多 Celery worker 进程的 NodeRegistry 保持同步

依赖:
- Redis (settings.redis_url)
- 与 sandbox 共享 Redis client (services.cache.get_cache_client)
"""

from __future__ import annotations

import asyncio
from typing import Any

from hscredit_studio.core.logging import get_logger

_log = get_logger(__name__)

# pub/sub 频道名
CHANNEL_NODE_RELOAD = "node:reload"

# 全局状态
_listener_task: asyncio.Task | None = None
_redis_client: Any = None


async def publish_node_reload(node_type: str, action: str = "reload") -> int:
    """发布 reload 消息.

    Args:
        node_type: 节点类型
        action: 'reload' / 'remove' / 'disable'

    Returns:
        订阅者数量 (int, Redis publish 返回值)
    """
    try:
        client = await _get_redis()
        message = f"{action}:{node_type}"
        result = await client.publish(CHANNEL_NODE_RELOAD, message)
        _log.info(
            "node_reload_published",
            channel=CHANNEL_NODE_RELOAD,
            message=message,
            subscribers=result,
        )
        return result
    except Exception as e:
        _log.warning("node_reload_publish_failed", error=str(e)[:200])
        return 0


async def start_reload_listener() -> None:
    """启动 Redis pub/sub 监听 (后台 task)."""
    global _redis_client
    try:
        _redis_client = await _get_redis()
        pubsub = _redis_client.pubsub()
        await pubsub.subscribe(CHANNEL_NODE_RELOAD)
        _log.info("node_reload_listener_started", channel=CHANNEL_NODE_RELOAD)

        # 持续监听
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")
            await _handle_message(data)

    except asyncio.CancelledError:
        _log.info("node_reload_listener_cancelled")
        raise
    except Exception as e:
        _log.warning("node_reload_listener_error", error=str(e)[:200])


async def stop_reload_listener() -> None:
    """停止 Redis pub/sub 监听."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception:
            pass
        _redis_client = None


async def _handle_message(data: str) -> None:
    """处理收到的一条 reload 消息."""
    # 格式: "action:node_type" 例如 "reload:my_filter_v1"
    if not data or ":" not in data:
        return
    action, node_type = data.split(":", 1)
    _log.info(
        "node_reload_received",
        action=action,
        node_type=node_type,
    )

    # 重新加载单个节点
    try:
        from hscredit_studio.core.database import async_session_maker
        from hscredit_studio.nodes.loader import reload_one_node_type
        async with async_session_maker() as session:
            ok = await reload_one_node_type(session, node_type)
        _log.info(
            "node_reload_applied",
            node_type=node_type,
            success=ok,
        )
    except Exception as e:
        _log.warning(
            "node_reload_apply_failed",
            node_type=node_type,
            error=str(e)[:200],
        )


async def _get_redis() -> Any:
    """获取 Redis async client (复用 services.cache 或新建)."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        from hscredit_studio.services.cache import get_cache_client
        _redis_client = await get_cache_client()
        return _redis_client
    except Exception as e:
        _log.warning("redis_get_failed", error=str(e)[:200])
        raise


__all__ = [
    "CHANNEL_NODE_RELOAD",
    "publish_node_reload",
    "start_reload_listener",
    "stop_reload_listener",
]
