/**
 * 审计 API — 审计事件查询 / 统计 / 导出.
 */

import { apiClient } from './client';
import type { PaginatedResponse } from '@/types';

export interface AuditEvent {
  event_id: string;
  tenant_id: string;
  user_id: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  occurred_at: string;
}

export interface AuditStats {
  total_events: number;
  unique_users: number;
  unique_actions: number;
  last_24h_events: number;
  last_7d_events: number;
  by_action: Array<{ action: string; count: number }>;
  by_user: Array<{ user_id: string | null; email: string; count: number }>;
}

export interface ListAuditEventsParams {
  user_id?: string;
  action?: string;
  resource_type?: string;
  resource_id?: string;
  since?: string;
  until?: string;
  page?: number;
  page_size?: number;
}

export const auditApi = {
  /**
   * 分页查询审计事件.
   */
  list: async (params: ListAuditEventsParams = {}): Promise<PaginatedResponse<AuditEvent>> => {
    const response = await apiClient.get<PaginatedResponse<AuditEvent>>(
      '/audit-events',
      { params },
    );
    return response.data;
  },

  /**
   * 审计统计概览 (运营 Dashboard 用).
   */
  stats: async (): Promise<AuditStats> => {
    const response = await apiClient.get<AuditStats>('/audit-events/stats');
    return response.data;
  },

  /**
   * 下载 CSV 导出.
   * 后端直接返回 text/csv 流, 前端用 Blob 触发浏览器下载.
   */
  exportCsv: async (params: { since?: string; until?: string } = {}): Promise<Blob> => {
    const response = await apiClient.get('/audit-events/export', {
      params,
      responseType: 'blob',
    });
    return response.data as Blob;
  },
};