"""Redis 缓存客户端 — 节点产物缓存 + 通用 KV.

依据 :file:`docs/design/06-non-functional.md` 第 6.2.2 节,
缓存键统一格式 ``{tenant_id}:{namespace}:{detail}``,
租户隔离是 key 的第一段。

主要功能:

- :func:`get_cache_client` — 全局 ``redis.asyncio.Redis`` 单例。
- :func:`close_cache_client` — 应用关闭时关闭连接。
- :class:`CacheKeyGenerator` — 统一命名空间,避免散落的字符串拼接。
- 序列化辅助函数(:func:`serialize_value` / :func:`serialize_json`)。

Phase 1 使用 ``pickle`` 序列化(可序列化任意 Python 对象);
Phase 2 计划迁移到 ``orjson`` 以提高安全性(参见
:file:`docs/design/06-non-functional.md` 第 6.7.2 节的 pickle 风险)。
"""
from __future__ import annotations

import hashlib
import json
import pickle
from typing import Any

import redis.asyncio as aioredis

from hscredit_studio.core.config import settings
from hscredit_studio.core.logging import get_logger

_log = get_logger(__name__)

_client: aioredis.Redis | None = None


async def get_cache_client() -> aioredis.Redis:
    """获取 Redis 客户端单例.

    第一次调用时建立连接池;之后所有调用复用同一个 ``Redis`` 实例。
    ``decode_responses=False`` 是因为我们要存 ``pickle`` / ``orjson`` 字节流,
    强制解码会破坏数据。
    """
    global _client
    if _client is None:
        _client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=False,
            max_connections=20,
            socket_timeout=5,
            socket_connect_timeout=3,
        )
        _log.info("redis_connected", url=settings.redis_url)
    return _client


async def close_cache_client() -> None:
    """关闭 Redis 连接(应用关闭时调用)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        _log.info("redis_closed")


class CacheKeyGenerator:
    """缓存键生成器 — 统一命名空间.

    全部方法 ``staticmethod``,按业务域划分:

    - :meth:`node_input_key` — 节点输入缓存(主用途)
    - :meth:`tenant_session`  — 租户会话
    - :meth:`rate_limit`     — 速率限制
    """

    @staticmethod
    def node_input_key(tenant_id: str, node_type: str, input_hash: str) -> str:
        """节点输入缓存键.

        格式: ``{tenant_id}:node:{node_type}:{input_hash}``.

        Args:
            tenant_id: 租户 UUID 字符串(anonymous 用于未登录请求)。
            node_type: 注册表里的节点类型(如 ``optimal_binning_chi``)。
            input_hash: 输入哈希(sha256 hex)。

        Returns:
            完整的 Redis 键。
        """
        return f"{tenant_id}:node:{node_type}:{input_hash}"

    @staticmethod
    def tenant_session(tenant_id: str, session_id: str) -> str:
        """租户会话键.

        格式: ``{tenant_id}:session:{session_id}``.
        """
        return f"{tenant_id}:session:{session_id}"

    @staticmethod
    def rate_limit(tenant_id: str, scope: str) -> str:
        """速率限制键.

        格式: ``{tenant_id}:ratelimit:{scope}``.
        ``scope`` 可以是 ``"api"`` / ``"run_submit"`` 等。
        """
        return f"{tenant_id}:ratelimit:{scope}"


# ===== 序列化辅助 =====


def serialize_value(value: Any) -> bytes:
    """用 ``pickle`` 序列化任意 Python 对象.

    .. warning::
        pickle 反序列化存在代码执行风险;仅用于受信任的内部缓存
        (即 key 不会被未授权用户预测到)。反序列化产物时
        必须校验 sha256 + 路径在当前租户桶内,见
        :file:`docs/design/06-non-functional.md` 第 6.7.2 节。
    """
    return pickle.dumps(value)


def deserialize_value(data: bytes) -> Any:
    """反序列化 pickle 对象.

    .. warning::
        仅反序列化本系统自身写入的数据;不接受用户输入的字节流。
    """
    return pickle.loads(data)  # noqa: S301 — trusted internal cache


# Phase 2 改进:使用 orjson 替代 pickle 以提高安全性。
# 以下两个函数是迁移目标接口,Phase 1 暂未启用。
def serialize_json(value: Any) -> bytes:
    """用 ``orjson`` 序列化 JSON 兼容对象.

    Phase 2 启用后会替代 ``serialize_value``;
    优点:不可执行代码、跨语言兼容、性能更高。
    """
    import orjson

    return orjson.dumps(value, default=str)


def deserialize_json(data: bytes) -> Any:
    """反序列化 orjson 字节流."""
    import orjson

    return orjson.loads(data)


__all__ = [
    "get_cache_client",
    "close_cache_client",
    "CacheKeyGenerator",
    "serialize_value",
    "deserialize_value",
    "serialize_json",
    "deserialize_json",
]