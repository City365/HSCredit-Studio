/** BI 报表导出 API 客户端 — Phase 7 B33.

API 列表:
- GET /bi-exports/datasets
- GET /bi-exports/views
- GET /bi-exports/stream/{dataset}
- GET /bi-exports/export/{dataset}?format=csv|ndjson|parquet
- GET /bi-exports/connectors/powerbi
- GET /bi-exports/connectors/tableau
- GET /bi-exports/connectors/finebi
- GET /bi-exports/connectors/test/{connector}
*/
import { apiClient } from './client';

export interface BIDataset {
  key: string;
  name: string;
  description: string;
  fields: string[];
  estimated_rows: number;
  supports_streaming: boolean;
  supports_parquet: boolean;
}

export interface BIView {
  name: string;
  schema: string;
  description: string;
  columns: string[];
}

export const biExportsApi = {
  listDatasets: async () =>
    (await apiClient.get<{ items: BIDataset[]; total: number }>('/bi-exports/datasets')).data,

  listViews: async () =>
    (await apiClient.get<{ items: BIView[]; total: number }>('/bi-exports/views')).data,

  streamNdjson: async (dataset: string, params?: { since?: string; until?: string }) =>
    (await apiClient.get(`/bi-exports/stream/${dataset}`, {
      params,
      responseType: 'blob',
    })).data,

  exportCsv: async (dataset: string, params?: { since?: string; until?: string }) =>
    (await apiClient.get(`/bi-exports/export/${dataset}`, {
      params: { format: 'csv', ...params },
      responseType: 'blob',
    })).data,

  exportNdjson: async (dataset: string, params?: { since?: string; until?: string }) =>
    (await apiClient.get(`/bi-exports/export/${dataset}`, {
      params: { format: 'ndjson', ...params },
      responseType: 'blob',
    })).data,

  exportParquet: async (dataset: string, params?: { since?: string; until?: string }) =>
    (await apiClient.get(`/bi-exports/export/${dataset}`, {
      params: { format: 'parquet', ...params },
      responseType: 'blob',
    })).data,

  getPowerBITemplate: async (params: { tenant_slug: string; tenant_uuid: string; base_url?: string }) =>
    (await apiClient.get<{
      tenant_id: string;
      tenant_slug: string;
      base_url: string;
      queries: Array<{ name: string; display_name: string; m_query: string; description: string }>;
      import_instructions: string;
    }>('/bi-exports/connectors/powerbi', { params })).data,

  getTableauTemplate: async (params: { tenant_slug: string; tenant_uuid: string; server?: string; port?: number; database?: string; username?: string }) =>
    (await apiClient.get<{
      tenant_id: string;
      schema_xml: string;
      import_instructions: string;
    }>('/bi-exports/connectors/tableau', { params })).data,

  getFineBITemplate: async (params: { tenant_slug: string; tenant_uuid: string }) =>
    (await apiClient.get<{
      tenant_id: string;
      display_name_zh: string;
      tables: Array<{ table_name: string; display_name: string; sql: string; fields: string[] }>;
      config_xml: string;
      import_instructions_zh: string;
    }>('/bi-exports/connectors/finebi', { params })).data,

  testConnector: async (connector: 'powerbi' | 'tableau' | 'finebi') =>
    (await apiClient.get<{
      connector: string;
      healthy: boolean;
      message: string;
      tested_at: string;
    }>(`/bi-exports/connectors/test/${connector}`)).data,

  // 触发浏览器下载
  downloadExport: async (dataset: string, format: 'csv' | 'ndjson' | 'parquet'): Promise<void> => {
    const response =
      format === 'csv'
        ? await biExportsApi.exportCsv(dataset)
        : format === 'ndjson'
          ? await biExportsApi.exportNdjson(dataset)
          : await biExportsApi.exportParquet(dataset);
    const url = window.URL.createObjectURL(new Blob([response as BlobPart]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `bi_${dataset}_${Date.now()}.${format}`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};