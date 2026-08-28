/** 行业模板 API — Phase 6 B30. */
import { apiClient } from './client';

export interface IndustryTemplate {
  template_id: string;
  name: string;
  industry: string;
  description: string;
  node_count: number;
  recommended_features: string[];
  model_type: string;
  target_column: string;
}

export interface IndustryTemplateDetail extends IndustryTemplate {
  nodes: Array<{ id: string; type: string; params: Record<string, unknown> }>;
  edges: Array<{ source: string; target: string }>;
  default_dataset: string;
  score_formula: string;
}

export const industryTemplatesApi = {
  list: async () =>
    (await apiClient.get<{ items: IndustryTemplate[]; total: number }>('/industry-templates')).data,

  get: async (id: string) =>
    (await apiClient.get<IndustryTemplateDetail>(`/industry-templates/${id}`)).data,

  instantiate: async (data: { template_id: string; workflow_name?: string; tenant_id?: string }) =>
    (await apiClient.post<{
      workflow_id: string;
      workflow_name: string;
      nodes_count: number;
      status: string;
    }>('/industry-templates/instantiate', data)).data,

  rate: async (id: string, data: { score: number; comment?: string }) =>
    (await apiClient.post(`/industry-templates/${id}/rate`, data)).data,
};