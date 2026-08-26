/**
 * WebSocket 客户端 — 自动重连 + JWT 鉴权.
 *
 * 用法：
 *   const { status, send } = useWebSocket({
 *     url: `/ws/${tenantSlug}/runs/${runId}`,
 *     onMessage: (event) => { ... },
 *   });
 *
 * 设计要点：
 *   - 通过 query string 传递 access_token: `?token=<jwt>`
 *   - 通过 authStore 实时读取 token，token 失效（401 → clearAuth）后下一次连接尝试失败并停止
 *   - 简单定时重连（Phase 1）：固定 reconnectInterval 上限 N 次；Phase 2 将切换为指数退避
 *   - `onMessage` 通过 ref 注入，避免因函数引用变化触发重连
 *   - 仅在 `url` 变化时重建连接（其他依赖通过 ref 读取）
 */

import { useEffect, useRef, useState } from 'react';

import { useAuthStore } from '@/stores/authStore';
import type { WSEvent } from '@/types';

export type WSConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export interface UseWebSocketOptions {
  /** 完整 WS URL（含 ws:// 或 wss://），可为 null（关闭连接）.*/
  url: string | null;
  /** 消息回调（JSON.parse 后传入）.*/
  onMessage?: (event: WSEvent) => void;
  /** 重连间隔（毫秒），Phase 1 使用固定值. */
  reconnectInterval?: number;
  /** 最大重连次数. */
  maxReconnectAttempts?: number;
}

/**
 * 拼接 token 查询参数.
 *
 * 若 url 已含 `?`，追加 `&token=`，否则追加 `?token=`.
 */
function appendToken(url: string, token: string): string {
  return url.includes('?') ? `${url}&token=${token}` : `${url}?token=${token}`;
}

export function useWebSocket(options: UseWebSocketOptions): {
  status: WSConnectionStatus;
  send: (data: unknown) => void;
} {
  const {
    url,
    onMessage,
    reconnectInterval = 3000,
    maxReconnectAttempts = 10,
  } = options;

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedByUserRef = useRef(false);
  const [status, setStatus] = useState<WSConnectionStatus>('disconnected');

  /** 始终读取最新的 onMessage，避免回调闭包陈旧. */
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    if (!url) {
      return undefined;
    }

    closedByUserRef.current = false;

    const connect = (): void => {
      // 每次重连前读取最新 token
      const accessToken = useAuthStore.getState().accessToken;
      if (!accessToken) {
        setStatus('error');
        return;
      }

      const fullUrl = appendToken(url, accessToken);
      let ws: WebSocket;
      try {
        ws = new WebSocket(fullUrl);
      } catch {
        setStatus('error');
        scheduleReconnect();
        return;
      }

      wsRef.current = ws;
      setStatus('connecting');

      ws.onopen = (): void => {
        setStatus('connected');
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event: MessageEvent): void => {
        try {
          const parsed: WSEvent = JSON.parse(event.data as string) as WSEvent;
          onMessageRef.current?.(parsed);
        } catch (e) {
          // eslint-disable-next-line no-console
          console.error('Failed to parse WS message', e);
        }
      };

      ws.onerror = (): void => {
        setStatus('error');
      };

      ws.onclose = (): void => {
        setStatus('disconnected');
        wsRef.current = null;
        if (!closedByUserRef.current) {
          scheduleReconnect();
        }
      };
    };

    const scheduleReconnect = (): void => {
      if (reconnectAttemptsRef.current >= maxReconnectAttempts) return;
      reconnectAttemptsRef.current += 1;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = setTimeout(connect, reconnectInterval);
    };

    connect();

    return (): void => {
      closedByUserRef.current = true;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch {
          /* ignore */
        }
        wsRef.current = null;
      }
    };
  }, [url, reconnectInterval, maxReconnectAttempts]);

  const send = (data: unknown): void => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data));
    }
  };

  return { status, send };
}