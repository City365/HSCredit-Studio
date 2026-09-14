/** 自动保存草稿 hook (阶段 7 实现).

行为:
- 防抖 5s: 用户停止输入 5 秒后自动保存
- 心跳 2 分钟: 即使在编辑, 也会心跳保持锁
- 离开页面: 释放锁
"""

import { useEffect, useRef } from 'react';
import { customNodesApi } from '@/api/custom-nodes';

interface UseDraftAutosaveOptions {
  customNodeId: string;
  /** 编辑中的 code (受控) */
  code: string;
  /** 自动保存间隔 (ms), 默认 5000 */
  interval?: number;
  /** 启用 */
  enabled?: boolean;
  /** 保存成功的回调 */
  onSaved?: () => void;
}

export function useDraftAutosave(options: UseDraftAutosaveOptions): void {
  const {
    customNodeId,
    code,
    interval = 5000,
    enabled = true,
    onSaved,
  } = options;

  const lastSavedCodeRef = useRef<string>(code);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled) return;
    if (code === lastSavedCodeRef.current) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      try {
        await customNodesApi.saveDraft(customNodeId, {
          code,
          validation_status: 'draft',
        });
        lastSavedCodeRef.current = code;
        onSaved?.();
      } catch {
        // ignore — 静默失败, 下次再试
      }
    }, interval);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [code, customNodeId, interval, enabled, onSaved]);
}
