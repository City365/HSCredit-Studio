/**
 * 工作流 API.
 *
 * 涵盖：CRUD、版本管理、导入/导出.
 * 所有请求路径均以 `/workflows` 开头，由 `client.ts` 拦截器自动注入 `/{tenantSlug}` 前缀.
 */

import { apiClient } from './client';
import type {
  PaginatedResponse,
  Workflow,
  WorkflowCreate,
  WorkflowDefinition,
  WorkflowUpdate,
  WorkflowVersion,
} from '@/types';

export interface ListWorkflowsParams {
  page?: number;
  page_size?: number;
  search?: string;
  tags?: string[];
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

/** 将参数对象序列化为 URLSearchParams（处理数组参数 tags=a&tags=b）.*/
function buildQueryString(params: Record<string, unknown>): string {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null) return;
    if (Array.isArray(v)) {
      v.forEach((item) => searchParams.append(k, String(item)));
    } else {
      searchParams.append(k, String(v));
    }
  });
  const qs = searchParams.toString();
  return qs ? `?${qs}` : '';
}

export const workflowsApi = {
  /** 工作流列表（分页 + 过滤 + 排序）.*/
  list: async (
    params: ListWorkflowsParams = {},
  ): Promise<PaginatedResponse<Workflow>> => {
    const response = await apiClient.get<PaginatedResponse<Workflow>>(
      `/workflows${buildQueryString(params as Record<string, unknown>)}`,
    );
    return response.data;
  },

  /** 单个工作流详情. */
  get: async (id: string): Promise<Workflow> => {
    const response = await apiClient.get<Workflow>(`/workflows/${id}`);
    return response.data;
  },

  /** 创建工作流. */
  create: async (data: WorkflowCreate): Promise<Workflow> => {
    const response = await apiClient.post<Workflow>('/workflows', data);
    return response.data;
  },

  /** 部分更新工作流. */
  update: async (id: string, data: WorkflowUpdate): Promise<Workflow> => {
    const response = await apiClient.patch<Workflow>(`/workflows/${id}`, data);
    return response.data;
  },

  /** 删除工作流. */
  delete: async (id: string): Promise<void> => {
    await apiClient.delete<void>(`/workflows/${id}`);
  },

  /** 列出工作流的所有版本. */
  listVersions: async (id: string): Promise<WorkflowVersion[]> => {
    const response = await apiClient.get<WorkflowVersion[]>(`/workflows/${id}/versions`);
    return response.data;
  },

  /** 创建新版本（fork 自当前 definition，可附带变更摘要）.*/
  createVersion: async (
    id: string,
    definition: WorkflowDefinition,
    changeSummary?: string,
  ): Promise<WorkflowVersion> => {
    const response = await apiClient.post<WorkflowVersion>(`/workflows/${id}/versions`, {
      definition,
      change_summary: changeSummary,
    });
    return response.data;
  },

  /** 获取指定版本. */
  getVersion: async (id: string, versionNumber: number): Promise<WorkflowVersion> => {
    const response = await apiClient.get<WorkflowVersion>(
      `/workflows/${id}/versions/${versionNumber}`,
    );
    return response.data;
  },

  /** 导出工作流（含所有 definition）.*/
  export: async (id: string): Promise<unknown> => {
    const response = await apiClient.get<unknown>(`/workflows/${id}/export`);
    return response.data;
  },

  /** 导入工作流（payload 为先前 export 的结果）.*/
  import: async (payload: unknown, name?: string): Promise<Workflow> => {
    const response = await apiClient.post<Workflow>('/workflows/import', { payload, name });
    return response.data;
  },
};