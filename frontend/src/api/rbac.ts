/** RBAC API — Phase 6 B28. */
import { apiClient } from './client';

export interface RbacRoleInfo {
  role: string;
  label: string;
  rank: number;
  is_tenant_scoped: boolean;
  description: string;
}

export interface PermissionMatrix {
  roles: RbacRoleInfo[];
  resources: string[];
  matrix: Record<string, Record<string, string | null>>;
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
    (await apiClient.get<PermissionMatrix>('/rbac/matrix')).data,

  getMenu: async () =>
    (await apiClient.get<{ menu: Array<{ key: string; label: string; icon?: string }> }>(
      '/rbac/menu',
    )).data,

  check: async (data: { resource: string; action: string }) =>
    (await apiClient.post<{ allowed: boolean; reason?: string }>('/rbac/check', data)).data,

  listPolicies: async () =>
    (await apiClient.get<{ items: RolePolicy[]; total: number }>('/rbac/policies')).data,

  createPolicy: async (data: Partial<RolePolicy>) =>
    (await apiClient.post<RolePolicy>('/rbac/policies', data)).data,

  listAudit: async () =>
    (await apiClient.get<{ items: RoleAuditItem[]; total: number }>('/rbac/audit')).data,
};