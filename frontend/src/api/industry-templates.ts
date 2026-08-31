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

  /** 一键实例化 — 后端返回 template_name + node_count + edge_count. */
  instantiate: async (data: { template_id: string; workflow_name?: string }) => {
    const { template_id, workflow_name } = data;
    void template_id; // template_id already in path
    const r = await apiClient.post<{
      template_id: string;
      template_name: string;
      workflow_id: string;
      workflow_name: string;
      node_count: number;
      edge_count: number;
      created_at: string;
    }>(`/industry-templates/${template_id}/instantiate`, { workflow_name });
    return r.data;
  },

  rate: async (id: string, data: { score: number; comment?: string }) =>
    (await apiClient.post(`/industry-templates/${id}/rate`, data)).data,
};