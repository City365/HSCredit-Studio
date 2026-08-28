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
  recipient: string;
  events: string[];
  active: boolean;
}

export interface NotificationLog {
  log_id: string;
  config_id: string;
  template_key: string;
  channel: string;
  recipient: string;
  status: string;
  sent_at: string;
  error: string | null;
}

export const notificationsApi = {
  listTemplates: async () =>
    (await apiClient.get<{ items: NotificationTemplate[]; total: number }>('/templates')).data,

  listConfigs: async () =>
    (await apiClient.get<{ items: NotificationConfig[]; total: number }>('/configs')).data,

  createConfig: async (data: Partial<NotificationConfig>) =>
    (await apiClient.post<NotificationConfig>('/configs', data)).data,

  sendTest: async (data: { template_key: string; recipient?: string; dry_run?: boolean }) =>
    (await apiClient.post<{
      template: string;
      results: Array<{ success: boolean; channel: string; error?: string }>;
    }>('/test', data)).data,

  listLogs: async () =>
    (await apiClient.get<{ items: NotificationLog[]; total: number }>('/logs')).data,
};