/**
 * 节点定义 API — 前端节点库动态加载.
 *
 * 数据来自后端 `GET /api/v1/{tenant}/node-definitions`，由 NodeRegistry 在启动
 * 时同步到 `node_definitions` 表。前端**禁止**硬编码节点列表.
 *
 * @see backend/hscredit_studio/api/v1/nodes.py
 */

import { apiClient } from './client';
import type { NodeDefinition } from '@/types';

export interface ListNodeDefinitionsParams {
  category?: string;
  search?: string;
  enabled_only?: boolean;
  include_contract?: boolean;
  sort_by?: 'node_type' | 'category' | 'name' | 'updated_at';
  sort_order?: 'asc' | 'desc';
}

export interface NodeDefinitionListResponse {
  definitions: NodeDefinition[];
}

/** 将参数对象序列化为 URLSearchParams（处理数组参数 tags=a&tags=b）.*/
function buildQueryString(params: Record<string, unknown>): string {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null) return;
    if (v === false) return; // 不传 enabled_only=false，省得 URL 噪声
    if (Array.isArray(v)) {
      v.forEach((item) => searchParams.append(k, String(item)));
    } else {
      searchParams.append(k, String(v));
    }
  });
  const qs = searchParams.toString();
  return qs ? `?${qs}` : '';
}

export interface NodeMetaUpdate {
  name?: string;
  description?: string;
  icon?: string;
}

export interface NodeToggleResponse {
  node_type: string;
  enabled: boolean;
  updated_at: string;
}

export interface SyncResultResponse {
  synced: number;
  added: number;
  updated: number;
  removed: number;
}

export const nodesApi = {
  /**
   * 列出节点定义（前端节点库主入口）.
   *
   * 默认 `include_contract=true` — 节点库需要 contract.params 来渲染参数表单.
   * 浏览器侧 React Query 缓存 30s staleTime（见 useApi 默认值），重复访问零请求.
   */
  list: async (
    params: ListNodeDefinitionsParams = {},
  ): Promise<NodeDefinition[]> => {
    const response = await apiClient.get<NodeDefinitionListResponse>(
      `/node-definitions${buildQueryString(params as Record<string, unknown>)}`,
    );
    return response.data.definitions;
  },

  /**
   * 按分类获取节点（节点库左侧分组）.
   * 便捷方法，内部走 list + 客户端过滤.
   */
  listByCategory: async (category: string): Promise<NodeDefinition[]> => {
    return nodesApi.list({ category, enabled_only: true });
  },

  // ===== Phase 6 B36: 系统节点管理 =====
  get: async (nodeType: string): Promise<NodeDefinition> => {
    const response = await apiClient.get<NodeDefinition>(`/node-definitions/${nodeType}`);
    return response.data;
  },

  enable: async (nodeType: string): Promise<NodeToggleResponse> => {
    const response = await apiClient.put<NodeToggleResponse>(
      `/node-definitions/${nodeType}/enable`,
    );
    return response.data;
  },

  disable: async (nodeType: string): Promise<NodeToggleResponse> => {
    const response = await apiClient.put<NodeToggleResponse>(
      `/node-definitions/${nodeType}/disable`,
    );
    return response.data;
  },

  updateMeta: async (
    nodeType: string,
    payload: NodeMetaUpdate,
  ): Promise<NodeDefinition> => {
    const response = await apiClient.put<NodeDefinition>(
      `/node-definitions/${nodeType}/meta`,
      payload,
    );
    return response.data;
  },

  sync: async (): Promise<SyncResultResponse> => {
    const response = await apiClient.post<SyncResultResponse>('/node-definitions/sync');
    return response.data;
  },
};
