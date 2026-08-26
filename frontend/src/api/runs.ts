/**
 * Run 执行 API.
 *
 * 涵盖：提交 Run、列表、详情、节点执行列表、取消.
 */

import { apiClient } from './client';
import type {
  Artifact,
  ArtifactListResponse,
  NodeExecution,
  NodeExecutionStatus,
  PaginatedResponse,
  Run,
  RunCancelResponse,
  RunStatus,
  RunSubmitRequest,
} from '@/types';

export interface ListRunsParams {
  page?: number;
  page_size?: number;
  workflow_id?: string;
  status?: RunStatus;
}

export interface ListArtifactsParams {
  include_download_url?: boolean;
  expires_in?: number;
}

function buildQueryString(params: Record<string, unknown>): string {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null) return;
    searchParams.append(k, String(v));
  });
  const qs = searchParams.toString();
  return qs ? `?${qs}` : '';
}

export const runsApi = {
  /** 提交工作流的一个 Run. */
  submit: async (
    workflowId: string,
    req: RunSubmitRequest = {},
  ): Promise<Run> => {
    const response = await apiClient.post<Run>(`/workflows/${workflowId}/runs`, req);
    return response.data;
  },

  /** 列出 Run（可按 workflow_id / status 过滤）.*/
  list: async (params: ListRunsParams = {}): Promise<PaginatedResponse<Run>> => {
    const response = await apiClient.get<PaginatedResponse<Run>>(
      `/runs${buildQueryString(params as Record<string, unknown>)}`,
    );
    return response.data;
  },

  /** 单个 Run 详情. */
  get: async (runId: string): Promise<Run> => {
    const response = await apiClient.get<Run>(`/runs/${runId}`);
    return response.data;
  },

  /** Run 下所有节点执行列表. */
  listNodeExecutions: async (runId: string): Promise<NodeExecution[]> => {
    const response = await apiClient.get<NodeExecution[]>(`/runs/${runId}/node-executions`);
    return response.data;
  },

  /** 单个节点执行详情. */
  getNodeExecution: async (runId: string, nodeExecId: string): Promise<NodeExecution> => {
    const response = await apiClient.get<NodeExecution>(
      `/runs/${runId}/node-executions/${nodeExecId}`,
    );
    return response.data;
  },

  /** 取消一个运行中的 Run. */
  cancel: async (runId: string): Promise<RunCancelResponse> => {
    const response = await apiClient.post<RunCancelResponse>(`/runs/${runId}/cancel`);
    return response.data;
  },

  /** 列出 Run 的所有产物（含预签名下载 URL）.*/
  listArtifacts: async (
    runId: string,
    params: ListArtifactsParams = {},
  ): Promise<Artifact[]> => {
    const response = await apiClient.get<ArtifactListResponse>(
      `/runs/${runId}/artifacts${buildQueryString(params as Record<string, unknown>)}`,
    );
    return response.data.artifacts;
  },

  /** 重试一个失败的节点执行. */
  retry: async (
    runId: string,
    nodeExecId: string,
  ): Promise<{ node_exec_id: string; run_id: string; status: NodeExecutionStatus; message: string }> => {
    const response = await apiClient.post<{
      node_exec_id: string;
      run_id: string;
      status: NodeExecutionStatus;
      message: string;
    }>(`/runs/${runId}/node-executions/${nodeExecId}/retry`);
    return response.data;
  },
};