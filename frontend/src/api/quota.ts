/** 配额与用量 API — Phase 4 B18/B19. */
import { apiClient } from './client';

export interface QuotaUsage {
  tenant_id: string;
  plan: string;
  monthly_runs_used: number;
  monthly_runs_limit: number;
  monthly_duration_ms_used: number;
  monthly_duration_ms_limit: number;
  monthly_storage_bytes_used: number;
  monthly_storage_gb_limit: number;
  ratio: number;
}

export interface TenantUsage {
  runs: number;
  duration_ms: number;
  storage_bytes: number;
  api_calls: number;
  by_node_type: Record<string, number>;
}

export const quotaApi = {
  get: async () =>
    (await apiClient.get<QuotaUsage>('')).data,
};

export const usageApi = {
  get: async (params?: { since?: string; until?: string }) =>
    (await apiClient.get<TenantUsage>('', { params })).data,
};