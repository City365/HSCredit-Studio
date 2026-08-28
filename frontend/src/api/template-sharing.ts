/** 模板共享 API — Phase 6 B31. */
import { apiClient } from './client';

export interface TemplateReviewLog {
  log_id: string;
  template_id: string;
  reviewer_id: string;
  old_status: string | null;
  new_status: string;
  comment: string | null;
  created_at: string;
}

export const templateSharingApi = {
  publish: async (data: {
    workflow_id: string;
    template_name: string;
    description?: string;
    tags?: string[];
    visibility?: 'private' | 'tenant' | 'public';
  }) =>
    (await apiClient.post<{
      template_id: string;
      review_status: string;
      source_workflow_id: string;
      node_count: number;
      edge_count: number;
      created_at: string;
    }>('/template-sharing/publish', data)).data,

  requestShare: async (id: string, data: { target_tenants: string[]; reason?: string }) =>
    (await apiClient.post(`/template-sharing/${id}/share`, data)).data,

  review: async (id: string, data: {
    approve: boolean;
    rejection_reason?: string;
    comment?: string;
    granted_tenants?: string[];
  }) => (await apiClient.post(`/template-sharing/${id}/review`, data)).data,

  listLogs: async (id: string) =>
    (await apiClient.get<{ items: TemplateReviewLog[]; total: number }>(
      `/template-sharing/${id}/logs`,
    )).data,
};