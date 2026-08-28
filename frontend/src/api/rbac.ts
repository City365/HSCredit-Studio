/** RBAC API — Phase 6 B28. */
import { apiClient } from './client';

export interface PermissionMatrix {
  roles: string[];
  resources: string[];
  actions: string[];
  matrix: Record<string, Record<string, string>>;
}

export interface RolePolicy {
  policy_id: string;
  role: string;
  resource: string;
  action: string;
  tenant_id: string | null;
}

export interface RoleAuditItem {
  audit_id: string;
  tenant_id: string;
  user_id: string;
  old_role: string | null;
  new_role: string;
  changed_by: string;
  reason: string | null;
  created_at: string;
}

export const rbacApi = {
  getMatrix: async () =>
    (await apiClient.get<PermissionMatrix>('/matrix')).data,

  getMenu: async () =>
    (await apiClient.get<{ menu: Array<{ key: string; label: string; icon?: string }> }>(
      '/menu',
    )).data,

  check: async (data: { resource: string; action: string }) =>
    (await apiClient.post<{ allowed: boolean; reason?: string }>('/check', data)).data,

  listPolicies: async () =>
    (await apiClient.get<{ items: RolePolicy[]; total: number }>('/policies')).data,

  createPolicy: async (data: Partial<RolePolicy>) =>
    (await apiClient.post<RolePolicy>('/policies', data)).data,

  listAudit: async () =>
    (await apiClient.get<{ items: RoleAuditItem[]; total: number }>('/audit')).data,
};