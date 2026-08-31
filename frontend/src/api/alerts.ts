/** 告警 API — Phase 5 B27. */
import { apiClient } from './client';

export interface AlertRule {
  rule_id: string;
  tenant_id: string | null;
  name: string;
  promql: string;
  for_duration: string;
  severity: 'info' | 'warning' | 'critical' | 'page';
  enabled: boolean;
}

export interface AlertSilence {
  silence_id: string;
  tenant_id: string | null;
  matchers: Array<{ key: string; value: string }>;
  starts_at: string;
  ends_at: string;
  comment: string;
}

export const alertsApi = {
  listRules: async () =>
    (await apiClient.get<{ items: AlertRule[]; total: number }>('/alerts/rules')).data,

  createRule: async (data: Partial<AlertRule>) =>
    (await apiClient.post<AlertRule>('/alerts/rules', data)).data,

  listSilences: async () =>
    (await apiClient.get<{ items: AlertSilence[]; total: number }>('/alerts/silences')).data,

  createSilence: async (data: Partial<AlertSilence>) =>
    (await apiClient.post<AlertSilence>('/alerts/silences', data)).data,

  evaluate: async (data: { tenant_id?: string }) =>
    (await apiClient.post<{ fired_count: number; rules_evaluated: number }>(
      '/alerts/evaluate',
      data,
    )).data,

  ingestInstance: async (data: {
    alert_name: string;
    severity: string;
    fingerprint: string;
    labels?: Record<string, string>;
  }) =>
    (await apiClient.post('/alerts/instances', data)).data,

  getSeverities: async () =>
    (await apiClient.get<{ severities: string[] }>('/alerts/severities')).data,
};