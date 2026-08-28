/** 安全加固 API — Phase 5 B25. */
import { apiClient } from './client';

export interface SecurityMetrics {
  total_audit_events: number;
  failed_logins_24h: number;
  active_lockouts: number;
  open_vulnerabilities: number;
  ip_rules_count: number;
  chain_integrity: 'valid' | 'broken';
  last_chain_check_at: string;
}

export const securityApi = {
  metrics: async () =>
    (await apiClient.get<SecurityMetrics>('/metrics')).data,

  checkChain: async (data?: { since?: string }) =>
    (await apiClient.post<{
      status: 'valid' | 'broken';
      checkpoints_checked: number;
      first_invalid?: { checkpoint_id: string; detected_at: string };
    }>('/chain/checkpoint', data ?? {})).data,

  exportSiem: async (data: { since?: string; format?: 'cef' | 'leef' | 'json' }) =>
    (await apiClient.post('/siem/export', data, { responseType: 'blob' })).data,

  intrusionCheck: async (data: { payload: string; source_ip?: string }) =>
    (await apiClient.post<{
      blocked: boolean;
      threats: Array<{ rule: string; severity: string }>;
    }>('/intrusion/check', data)).data,

  passwordCheck: async (data: { password: string }) =>
    (await apiClient.post<{
      score: number;
      issues: string[];
      acceptable: boolean;
    }>('/password/check', data)).data,

  listIpRules: async () =>
    (await apiClient.get<{ items: unknown[]; total: number }>('/ip-rules')).data,

  createIpRule: async (data: { rule_type: string; pattern: string; description?: string }) =>
    (await apiClient.post('/ip-rules', data)).data,

  ipCheck: async (data: { ip: string }) =>
    (await apiClient.post<{ allowed: boolean; matched_rule?: string }>('/ip-check', data)).data,

  listVulnerabilities: async () =>
    (await apiClient.get<{ items: unknown[]; total: number }>('/vulnerabilities')).data,

  createVulnerability: async (data: Record<string, unknown>) =>
    (await apiClient.post('/vulnerabilities', data)).data,

  vulnerabilityStats: async () =>
    (await apiClient.get<{
      total: number;
      by_severity: Record<string, number>;
      by_status: Record<string, number>;
    }>('/vulnerabilities/stats')).data,
};