/** 通知配置 API — Phase 5 B23. */
import { apiClient } from './client';

export interface NotificationTemplate {
  key: string;
  title_template: string;
  body_template: string;
  default_channels: string[];
}

export interface NotificationConfig {
  config_id: string;
  tenant_id: string;
  channel: 'email' | 'slack' | 'wecom' | 'sms';
  template_key: string | null;
  recipient: string | null;
  enabled: boolean;
  created_at?: string;
}

export interface NotificationLog {
  log_id: string;
  template_key: string;
  channel: string;
  status: string;
  title: string;
  recipient: string | null;
  error: string | null;
  created_at: string;
}

interface ListTemplatesResp {
  templates: NotificationTemplate[];
  count: number;
}

interface ListConfigsResp {
  items: NotificationConfig[];
  count: number;
}

interface ListLogsResp {
  items: NotificationLog[];
  count: number;
}

export const notificationsApi = {
  listTemplates: async (): Promise<NotificationTemplate[]> => {
    const r = await apiClient.get<ListTemplatesResp>('/notifications/templates');
    return r.data.templates ?? [];
  },

  listConfigs: async (): Promise<NotificationConfig[]> => {
    const r = await apiClient.get<ListConfigsResp>('/notifications/configs');
    return r.data.items ?? [];
  },

  createConfig: async (data: {
    channel: string;
    template_key?: string;
    recipient?: string;
    enabled?: boolean;
  }): Promise<NotificationConfig> => {
    const r = await apiClient.post<NotificationConfig>('/notifications/configs', null, {
      params: data,
    });
    return r.data;
  },

  /** 测试发送 — 后端接收 Query 参数 (template_key, channel, recipient). */
  sendTest: async (data: {
    template_key: string;
    channel?: string;
    recipient?: string;
    dry_run?: boolean;
  }): Promise<{
    results: Array<{ success: boolean; channel: string; error?: string }>;
    log_id?: string;
  }> => {
    const r = await apiClient.post<{
      results: Array<{ success: boolean; channel: string; error?: string }>;
      log_id?: string;
    }>('/notifications/test', null, { params: data });
    return r.data;
  },

  listLogs: async (): Promise<NotificationLog[]> => {
    const r = await apiClient.get<ListLogsResp>('/notifications/logs');
    return r.data.items ?? [];
  },
};
