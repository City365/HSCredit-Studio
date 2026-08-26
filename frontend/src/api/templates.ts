/**
 * 模板 API.
 *
 * 涵盖：列表、详情、实例化（创建工作流）、评分.
 * 所有请求路径均以 `/templates` 开头，由 `client.ts` 拦截器自动注入 `/{tenantSlug}` 前缀.
 */

import { apiClient } from './client';
import type { PaginatedResponse, Workflow } from '@/types';

/** 单个模板（UI 卡片用）.*/
export interface Template {
  id: string;
  name: string;
  description?: string | null;
  category: string;
  icon?: string | null;
  tags: string[];
  visibility: string;
  use_count: number;
  rating_avg: number;
  rating_count: number;
  is_system: boolean;
}

/** 实例化模板请求体. */
export interface InstantiateTemplateRequest {
  workflow_name?: string;
  /** 节点参数覆盖 {node_id: {param: value}}. */
  params_overrides?: Record<string, Record<string, unknown>>;
}

/** 模板评分请求体. */
export interface RateTemplateRequest {
  /** 评分（1-5 整数）.*/
  rating: number;
  comment?: string;
}

/** 模板评分响应. */
export interface RateTemplateResponse {
  rating_id: string;
  rating: number;
}

/** 列表查询参数. */
export interface ListTemplatesParams {
  page?: number;
  page_size?: number;
  search?: string;
  category?: string;
}

/** 将参数对象序列化为 URLSearchParams（处理空值）.*/
function buildQueryString(params: Record<string, unknown>): string {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null) return;
    searchParams.append(k, String(v));
  });
  const qs = searchParams.toString();
  return qs ? `?${qs}` : '';
}

export const templatesApi = {
  /** 模板列表（分页 + 过滤）.*/
  list: async (params: ListTemplatesParams = {}): Promise<PaginatedResponse<Template>> => {
    const response = await apiClient.get<PaginatedResponse<Template>>(
      `/templates${buildQueryString(params as Record<string, unknown>)}`,
    );
    return response.data;
  },

  /** 单个模板详情. */
  get: async (id: string): Promise<Template> => {
    const response = await apiClient.get<Template>(`/templates/${id}`);
    return response.data;
  },

  /** 从模板实例化一个新工作流. */
  instantiate: async (
    id: string,
    req: InstantiateTemplateRequest = {},
  ): Promise<Workflow> => {
    const response = await apiClient.post<Workflow>(
      `/templates/${id}/instantiate`,
      req,
    );
    return response.data;
  },

  /** 提交或更新模板评分（1-5）.*/
  rate: async (id: string, req: RateTemplateRequest): Promise<RateTemplateResponse> => {
    const response = await apiClient.post<RateTemplateResponse>(
      `/templates/${id}/ratings`,
      req,
    );
    return response.data;
  },
};