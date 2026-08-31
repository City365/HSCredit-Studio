/** 超管后台 API — Phase 6 B29. */
import { apiClient } from './client';

export interface GlobalOverview {
  total_tenants: number;
  active_tenants: number;
  total_users: number;
  total_workflows: number;
  total_runs: number;
  recent_audit_count: number;
}

export interface TenantListItem {
  tenant_id: string;
  slug: string;
  name: string;
  plan: string;
  status: string;
  is_super_admin: boolean;
  user_count: number;
  workflow_count: number;
  health: 'healthy' | 'inactive' | 'warning';
  created_at: string;
}

export const adminApi = {
  overview: async () =>
    (await apiClient.get<GlobalOverview>('/admin/overview')).data,

  listTenants: async (params?: { search?: string; status?: string; page?: number }) =>
    (await apiClient.get<{ items: TenantListItem[]; total: number }>('/admin/tenants', { params })).data,

  getTenant: async (id: string) =>
    (await apiClient.get(`/admin/tenants/${id}`)).data,

  updateTenantStatus: async (id: string, data: { status: string; reason?: string }) =>
    (await apiClient.post(`/admin/tenants/${id}/status`, data)).data,

  migrateTenant: async (id: string, data: { target_cluster: string }) =>
    (await apiClient.post(`/admin/tenants/${id}/migrate`, data)).data,

  changeUserRole: async (uid: string, data: { new_role: string }) =>
    (await apiClient.post(`/admin/users/${uid}/role`, data)).data,
};