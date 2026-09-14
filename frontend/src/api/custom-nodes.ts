/**
 * 自定义节点 API — Phase 6 B36.
 *
 * 节点 CRUD / 版本 / 草稿 / 编辑锁 / 试运行
 *
 * @see backend/hscredit_studio/api/v1/custom_nodes.py
 */

import { apiClient } from './client';

// ===== 通用 =====

function buildQueryString(params: Record<string, unknown>): string {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null) return;
    if (v === false) return;
    if (Array.isArray(v)) {
      v.forEach((item) => searchParams.append(k, String(item)));
    } else {
      searchParams.append(k, String(v));
    }
  });
  const qs = searchParams.toString();
  return qs ? `?${qs}` : '';
}

// ===== 节点 CRUD =====

export type Visibility = 'private' | 'tenant' | 'public';
export type DraftValidationStatus = 'draft' | 'validating' | 'valid' | 'invalid';
export type TestRunStatus = 'success' | 'failed' | 'timeout' | 'oom';

export interface CustomNodeListItem {
  custom_node_id: string;
  node_type: string;
  name: string;
  category: string;
  visibility: Visibility;
  enabled: boolean;
  icon: string | null;
  current_version_number: number | null;
  test_run_count: number;
  last_test_run_at: string | null;
  updated_at: string;
}

export interface CustomNodeListResponse {
  items: CustomNodeListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface CustomNodeResponse {
  custom_node_id: string;
  tenant_id: string;
  node_type: string;
  name: string;
  category: string;
  description: string | null;
  icon: string | null;
  visibility: Visibility;
  enabled: boolean;
  contract: Record<string, unknown>;
  current_version_number: number | null;
  test_run_count: number;
  last_test_run_at: string | null;
  locked_by: string | null;
  locked_at: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomNodeCreateRequest {
  node_type: string;
  name: string;
  category?: string;
  description?: string;
  icon?: string;
  visibility?: Visibility;
  code: string;
  contract: Record<string, unknown>;
  requirements?: string;
}

export interface CustomNodeUpdateRequest {
  name?: string;
  category?: string;
  description?: string;
  icon?: string;
  visibility?: Visibility;
  enabled?: boolean;
}

export interface CustomNodeUpdateCodeRequest {
  code: string;
  contract: Record<string, unknown>;
  change_summary?: string;
}

// ===== 版本 =====

export interface CustomNodeVersionResponse {
  version_id: string;
  custom_node_id: string;
  version_number: number;
  code: string;
  contract: Record<string, unknown>;
  requirements: string | null;
  change_summary: string | null;
  created_by: string | null;
  created_at: string;
}

export interface CustomNodeVersionListResponse {
  items: CustomNodeVersionResponse[];
  total: number;
}

// ===== 草稿 =====

export interface CustomNodeDraftResponse {
  draft_id: string;
  custom_node_id: string;
  draft_code: string;
  draft_contract: Record<string, unknown>;
  contract_preview: Record<string, unknown> | null;
  validation_status: DraftValidationStatus;
  validation_issues: Record<string, unknown> | null;
  last_validation_at: string | null;
  updated_at: string;
}

export interface CustomNodeDraftRequest {
  code: string;
  contract_preview?: Record<string, unknown>;
  validation_status?: DraftValidationStatus;
  validation_issues?: Record<string, unknown>;
}

// ===== 编辑锁 =====

export interface CustomNodeLockResponse {
  lock_id: string;
  node_type: string;
  tenant_id: string;
  locked_by: string;
  locked_at: string;
  expires_at: string;
}

// ===== 校验 / 反推 / 试运行 =====

export interface ValidationIssue {
  line: number;
  column: number;
  severity: 'error' | 'warning';
  rule: string;
  message: string;
}

export interface ASTPreview {
  class_name: string | null;
  has_contract: boolean;
  has_run_method: boolean;
  run_signature: Record<string, unknown> | null;
  imports: string[];
  methods: string[];
  base_classes: string[];
}

export interface ValidateResponse {
  valid: boolean;
  issues: ValidationIssue[];
  ast_preview: ASTPreview | null;
}

export interface DetectContractResponse {
  draft_contract: Record<string, unknown>;
  ast_inferred: Record<string, unknown>;
  runtime_inferred: Record<string, unknown> | null;
  warnings: string[];
}

export interface TestRunRequest {
  version_id?: string;
  sample_inputs?: Record<string, unknown>;
  sample_params?: Record<string, unknown>;
  sample_data?: Record<string, unknown>;
}

export interface TestRunResponse {
  test_run_id: string;
  status: TestRunStatus;
  duration_ms: number;
  outputs?: Record<string, unknown> | null;
  logs: string[];
  resource_usage?: Record<string, unknown> | null;
  error?: Record<string, unknown> | null;
}

// ===== API 客户端 =====

export interface ListCustomNodesParams {
  category?: string;
  visibility?: Visibility;
  enabled_only?: boolean;
  search?: string;
  page?: number;
  page_size?: number;
}

export const customNodesApi = {
  // ===== 节点 CRUD =====
  list: async (params: ListCustomNodesParams = {}): Promise<CustomNodeListResponse> => {
    const response = await apiClient.get<CustomNodeListResponse>(
      `/custom-nodes${buildQueryString(params as Record<string, unknown>)}`,
    );
    return response.data;
  },

  get: async (customNodeId: string): Promise<CustomNodeResponse> => {
    const response = await apiClient.get<CustomNodeResponse>(
      `/custom-nodes/${customNodeId}`,
    );
    return response.data;
  },

  create: async (payload: CustomNodeCreateRequest): Promise<CustomNodeResponse> => {
    const response = await apiClient.post<CustomNodeResponse>('/custom-nodes', payload);
    return response.data;
  },

  update: async (
    customNodeId: string,
    payload: CustomNodeUpdateRequest,
  ): Promise<CustomNodeResponse> => {
    const response = await apiClient.put<CustomNodeResponse>(
      `/custom-nodes/${customNodeId}`,
      payload,
    );
    return response.data;
  },

  delete: async (customNodeId: string): Promise<void> => {
    await apiClient.delete(`/custom-nodes/${customNodeId}`);
  },

  updateCode: async (
    customNodeId: string,
    payload: CustomNodeUpdateCodeRequest,
  ): Promise<CustomNodeVersionResponse> => {
    const response = await apiClient.put<CustomNodeVersionResponse>(
      `/custom-nodes/${customNodeId}/code`,
      payload,
    );
    return response.data;
  },

  // ===== 版本 =====
  listVersions: async (customNodeId: string): Promise<CustomNodeVersionListResponse> => {
    const response = await apiClient.get<CustomNodeVersionListResponse>(
      `/custom-nodes/${customNodeId}/versions`,
    );
    return response.data;
  },

  getVersion: async (
    customNodeId: string,
    versionId: string,
  ): Promise<CustomNodeVersionResponse> => {
    const response = await apiClient.get<CustomNodeVersionResponse>(
      `/custom-nodes/${customNodeId}/versions/${versionId}`,
    );
    return response.data;
  },

  rollback: async (
    customNodeId: string,
    versionId: string,
  ): Promise<CustomNodeVersionResponse> => {
    const response = await apiClient.post<CustomNodeVersionResponse>(
      `/custom-nodes/${customNodeId}/versions/${versionId}/rollback`,
    );
    return response.data;
  },

  // ===== 草稿 =====
  getDraft: async (customNodeId: string): Promise<CustomNodeDraftResponse> => {
    const response = await apiClient.get<CustomNodeDraftResponse>(
      `/custom-nodes/${customNodeId}/draft`,
    );
    return response.data;
  },

  saveDraft: async (
    customNodeId: string,
    payload: CustomNodeDraftRequest,
  ): Promise<CustomNodeDraftResponse> => {
    const response = await apiClient.put<CustomNodeDraftResponse>(
      `/custom-nodes/${customNodeId}/draft`,
      payload,
    );
    return response.data;
  },

  discardDraft: async (customNodeId: string): Promise<void> => {
    await apiClient.delete(`/custom-nodes/${customNodeId}/draft`);
  },

  // ===== 编辑锁 =====
  acquireLock: async (customNodeId: string): Promise<CustomNodeLockResponse> => {
    const response = await apiClient.post<CustomNodeLockResponse>(
      `/custom-nodes/${customNodeId}/lock`,
    );
    return response.data;
  },

  releaseLock: async (customNodeId: string): Promise<void> => {
    await apiClient.delete(`/custom-nodes/${customNodeId}/lock`);
  },

  heartbeatLock: async (customNodeId: string): Promise<CustomNodeLockResponse> => {
    const response = await apiClient.post<CustomNodeLockResponse>(
      `/custom-nodes/${customNodeId}/lock/heartbeat`,
    );
    return response.data;
  },

  // ===== 校验 / 反推 / 试运行 =====
  validate: async (
    customNodeId: string,
    payload: { code: string },
  ): Promise<ValidateResponse> => {
    const response = await apiClient.post<ValidateResponse>(
      `/custom-nodes/${customNodeId}/validate`,
      payload,
    );
    return response.data;
  },

  detectContract: async (
    customNodeId: string,
    payload: { code: string; sample_data?: Record<string, unknown> },
  ): Promise<DetectContractResponse> => {
    const response = await apiClient.post<DetectContractResponse>(
      `/custom-nodes/${customNodeId}/detect-contract`,
      payload,
    );
    return response.data;
  },

  testRun: async (
    customNodeId: string,
    payload: TestRunRequest,
  ): Promise<TestRunResponse> => {
    const response = await apiClient.post<TestRunResponse>(
      `/custom-nodes/${customNodeId}/test`,
      payload,
    );
    return response.data;
  },
};
