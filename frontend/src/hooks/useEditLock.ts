/** 编辑锁 hook — 进入编辑页时申请锁, 心跳续期, 离开释放.
 *
 * 行为:
 * - mount → acquire
 * - 每 2 分钟 → heartbeat (只要 enabled)
 * - unmount → release (navigator.sendBeacon)
 */

import { useEffect, useRef } from 'react';
import { customNodesApi } from '@/api/custom-nodes';

interface UseEditLockOptions {
  customNodeId: string;
  /** 是否启用 (例如 isLoading 时不启用) */
  enabled?: boolean;
  /** 心跳间隔 (ms) */
  heartbeatInterval?: number;
}

export function useEditLock(options: UseEditLockOptions): void {
  const { customNodeId, enabled = true, heartbeatInterval = 120_000 } = options;
  const lockIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!enabled || !customNodeId) return;

    let cancelled = false;
    let heartbeatTimer: ReturnType<typeof setInterval> | null = null;

    const acquire = async () => {
      try {
        const lock = await customNodesApi.acquireLock(customNodeId);
        if (cancelled) {
          // 已被卸载, 立刻释放
          void customNodesApi.releaseLock(customNodeId);
          return;
        }
        lockIdRef.current = lock.lock_id;
        heartbeatTimer = setInterval(async () => {
          try {
            await customNodesApi.heartbeatLock(customNodeId);
          } catch {
            // 心跳失败 (锁过期或被回收), 停止
            if (heartbeatTimer) clearInterval(heartbeatTimer);
          }
        }, heartbeatInterval);
      } catch (e) {
        // 锁已被他人占用或失败, 不重试
        console.warn('edit lock acquire failed', e);
      }
    };
    void acquire();

    return () => {
      cancelled = true;
      if (heartbeatTimer) clearInterval(heartbeatTimer);
      // 释放锁 (用 sendBeacon 在关闭页面时也能发出请求)
      try {
        if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
          const url = `/api/v1/demo/custom-nodes/${customNodeId}/lock`;
          navigator.sendBeacon(new Request(url, { method: 'DELETE' }));
        } else {
          void customNodesApi.releaseLock(customNodeId);
        }
      } catch {
        // ignore
      }
    };
  }, [customNodeId, enabled, heartbeatInterval]);
}
