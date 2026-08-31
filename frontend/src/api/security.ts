/** 安全加固 API — Phase 5 B25. */
import { apiClient } from './client';

export interface SecurityMetrics {
  total_events?: number;
  failed_logins?: number;
  auth_failures?: number;
  sensitive_data_access?: number;
  data_exports?: number;
  permission_changes?: number;
  config_changes?: number;
  open_vulnerabilities?: number;
  ip_rules_count?: number;
  chain_integrity?: 'valid' | 'broken';
  last_chain_check_at?: string;
  top_actions?: Array<[string, number]>;
  top_ips?: Array<[string, number]>;
  window_days?: number;
}

export const securityApi = {
  metrics: async () =>
    (await apiClient.get<SecurityMetrics>('/security/metrics')).data,

  checkChain: async (data?: { since?: string }) =>
    (await apiClient.post<{
      status: 'valid' | 'broken';
      checkpoints_checked: number;
      first_invalid?: { checkpoint_id: string; detected_at: string };
    }>('/audit-integrity', data ?? {})).data,

  exportSiem: async (data: { since?: string; format?: 'cef' | 'leef' | 'json' }) =>
    (await apiClient.post('/security/export', data, { responseType: 'blob' })).data,

  intrusionCheck: async (data: { payload: string; source_ip?: string }) =>
    (await apiClient.post<{
      blocked: boolean;
      threats: Array<{ rule: string; severity: string }>;
    }>('/security/intrusion-check', data)).data,

  passwordCheck: async (data: { password: string }) =>
    (await apiClient.post<{
      score: number;
      issues: string[];
      acceptable: boolean;
    }>('/password/check', data)).data,

  listIpRules: async () =>
    (await apiClient.get<{ items: unknown[]; total: number }>('/security/ip-rules')).data,

  createIpRule: async (data: { rule_type: string; pattern: string; description?: string }) =>
    (await apiClient.post('/security/ip-rules', data)).data,

  ipCheck: async (data: { ip: string }) =>
    (await apiClient.post<{ allowed: boolean; matched_rule?: string }>('/security/ip-check', data)).data,

  listVulnerabilities: async () =>
    (await apiClient.get<{ items: unknown[]; total: number }>('/security/vulnerabilities')).data,

  createVulnerability: async (data: Record<string, unknown>) =>
    (await apiClient.post('/security/vulnerabilities', data)).data,

  vulnerabilityStats: async () =>
    (await apiClient.get<{
      total: number;
      by_severity: Record<string, number>;
      by_status: Record<string, number>;
    }>('/security/vulnerabilities/stats')).data,
};