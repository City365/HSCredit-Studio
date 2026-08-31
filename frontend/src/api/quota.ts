/** 配额与用量 API — Phase 4 B18/B19. */
import { apiClient } from './client';

export interface QuotaDimension {
  used: number;
  limit: number;
  unlimited: boolean;
  ratio: number;
}

export interface QuotaUsage {
  plan: string;
  monthly_runs: QuotaDimension;
  monthly_duration_ms: QuotaDimension;
  monthly_storage_gb: QuotaDimension;
}

export interface QuotaCheck {
  allowed: boolean;
  near_limit: boolean;
  exceeded_dim: string | null;
  message: string;
}

export interface QuotaResponse {
  snapshot: QuotaUsage;
  check: QuotaCheck;
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
    (await apiClient.get<QuotaResponse>('')).data,
};

export const usageApi = {
  get: async (params?: { since?: string; until?: string }) =>
    (await apiClient.get<TenantUsage>('', { params })).data,
};