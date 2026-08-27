"""WebSocket 端点 — 实时推送 Run / NodeExecution 状态.

依据 :file:`docs/design/01-system-architecture.md` 第 1.4 节,
本端点采用 ``/ws/runs/{run_id}?token=<jwt>`` URL 鉴权 + Redis pub/sub
解耦多 worker 推流。

事件流
------

``executor.coordinator`` 与 ``executor.tasks`` 在状态变更时向
``run:{run_id}`` channel 发布 JSON 事件,本端点负责:

1. JWT 鉴权(从 query string 取 ``token``)
2. 校验 ``tenant_id`` 与 run 一致(防越权)
3. 订阅 Redis pub/sub,转发 ``WSEvent`` 到客户端
4. 客户端断开 / token 失效时优雅清理
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError

from hscredit_studio.core.config import settings
from hscredit_studio.core.database import session_scope
from hscredit_studio.core.logging import get_logger
from hscredit_studio.core.security import decode_token
from hscredit_studio.models import Run

router = APIRouter(tags=["WebSocket"])
_log = get_logger(__name__)

# 客户端发送 ping 的间隔 (秒)
_PING_INTERVAL = 25
# pubsub get_message 超时 (秒)
_PUBSUB_TIMEOUT = 1.0
# 服务端发送 keep-alive 的间隔 (秒)
_KEEPALIVE_INTERVAL = 15


async def _verify_jwt(token: str) -> dict[str, Any] | None:
    """解码 JWT 并校验 type=access,返回 claims 或 None."""
    try:
        payload = decode_token(token)
    except (ValueError, JWTError) as e:
        _log.warning("ws_jwt_invalid", error=str(e))
        return None
    if payload.get("type") != "access":
        _log.warning("ws_jwt_wrong_type", type=payload.get("type"))
        return None
    return payload


async def _verify_run_access(run_id: UUID, claims: dict[str, Any]) -> bool:
    """校验 JWT 中的 tenant_id 与 run.tenant_id 一致."""
    jwt_tenant = claims.get("tenant_id")
    if not jwt_tenant:
        return False
    try:
        jwt_tenant_uuid = UUID(jwt_tenant)
    except (ValueError, TypeError):
        return False
    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return False
        return run.tenant_id == jwt_tenant_uuid


def _build_event(event_type: str, run_id: str, **payload: Any) -> dict[str, Any]:
    """构造 WSEvent dict（前端 WSEvent 类型对应）."""
    return {"type": event_type, "run_id": str(run_id), **payload}


@router.websocket("/runs/{run_id}")
async def run_status_ws(
    websocket: WebSocket,
    run_id: UUID,
    token: str = Query(..., description="JWT access token"),
) -> None:
    """WebSocket: 实时推送 run / node_execution 状态 + 日志流.

    客户端连接示例::

        ws = new WebSocket(`ws://host/ws/runs/${run_id}?token=${jwt}`)

    接收的事件类型（与前端 :file:`useWebSocket.ts` 一致）:
        - ``run_status``: Run 状态变化
        - ``node_execution``: 节点执行状态变化
        - ``log``: 节点日志（stdout / stderr / system 三类）
    """
    # 1. JWT 鉴权
    claims = await _verify_jwt(token)
    if claims is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Run 存在性 + 租户一致性
    if not await _verify_run_access(run_id, claims):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 3. 接受连接
    await websocket.accept()
    _log.info("ws_connected", run_id=str(run_id), user=claims.get("sub"))

    # 4. 订阅 Redis pub/sub
    pubsub = None
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=False)
        pubsub = redis_client.pubsub()
        channel = f"run:{run_id}"
        await pubsub.subscribe(channel)

        # 5. 双向循环：接收 client ping（可选）+ 推 pubsub 消息
        last_keepalive = asyncio.get_event_loop().time()
        while True:
            now = asyncio.get_event_loop().time()

            # 推 pubsub 消息
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=_PUBSUB_TIMEOUT)
            if msg and msg.get("type") == "message":
                try:
                    payload = msg["data"]
                    if isinstance(payload, (bytes, bytearray)):
                        payload = payload.decode("utf-8")
                    event = json.loads(payload)
                    await websocket.send_json(event)
                except Exception as e:
                    _log.warning("ws_send_failed", error=str(e), run_id=str(run_id))

            # 接收 client 消息（断开/ping），timeout 0
            try:
                client_msg = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=0.0,
                )
                # 客户端 ping/pong：收到任何文本就忽略
                _ = client_msg
            except TimeoutError:
                pass
            except WebSocketDisconnect:
                _log.info("ws_client_disconnected", run_id=str(run_id))
                break
            except Exception as e:
                _log.debug("ws_recv_unexpected", run_id=str(run_id), error=str(e))
                break

            # keep-alive（防止 idle 连接被中间设备关闭）
            if now - last_keepalive > _KEEPALIVE_INTERVAL:
                try:
                    await websocket.send_json(_build_event("ping", str(run_id), ts=now))
                    last_keepalive = now
                except Exception as e:
                    _log.debug("ws_keepalive_failed", run_id=str(run_id), error=str(e))
                    break

    except WebSocketDisconnect:
        _log.info("ws_disconnected", run_id=str(run_id))
    except Exception as e:
        _log.exception("ws_unexpected_error", run_id=str(run_id), error=str(e))
    finally:
        if pubsub is not None:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe()
                await pubsub.close()
        with contextlib.suppress(Exception):
            await redis_client.close()
        with contextlib.suppress(Exception):
            await websocket.close()
        _log.info("ws_closed", run_id=str(run_id))


__all__ = ["router"]
