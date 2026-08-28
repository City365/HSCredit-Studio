/** 模型导出 API 客户端 — Phase 7 B34.

API 列表:
- GET  /model-export/formats
- POST /model-export/export
- POST /model-export/validate
- POST /model-export/demo-model
*/
import { apiClient } from './client';

export interface ModelFormatInfo {
  format: 'pmml' | 'onnx';
  description: string;
  mime_type: string;
  supported_models: string[];
  tools: string[];
}

export interface ModelExportResponse {
  format: 'pmml' | 'onnx';
  model_type: 'sklearn' | 'scorecard' | 'lightgbm' | 'xgboost';
  filename: string;
  mime_type: string;
  file_size: number;
  content_b64: string;
  warnings: string[];
  exported_at: string;
}

export interface ModelValidationResponse {
  passed: boolean;
  max_abs_error: number;
  mean_abs_error: number;
  sample_count: number;
  message: string;
  tested_at: string;
  original_predictions: number[];
  exported_predictions: number[];
}

export interface DemoModelResponse {
  model_b64: string;
  feature_names: string[];
  coefficients: number[];
  intercept: number;
  description: string;
}

export const modelExportApi = {
  listFormats: async () =>
    (await apiClient.get<{ formats: ModelFormatInfo[]; tolerance_default: number }>(
      '/model-export/formats',
    )).data,

  exportModel: async (data: {
    model_b64: string;
    model_type: 'sklearn' | 'scorecard' | 'lightgbm' | 'xgboost';
    feature_names: string[];
    format: 'pmml' | 'onnx';
    description?: string;
  }) =>
    (await apiClient.post<ModelExportResponse>('/model-export/export', data)).data,

  validate: async (data: {
    original_model_b64: string;
    exported_format: 'pmml' | 'onnx';
    exported_content_b64: string;
    sample_inputs: number[][];
    tolerance?: number;
  }) => (await apiClient.post<ModelValidationResponse>('/model-export/validate', data)).data,

  generateDemoModel: async (data: { feature_names?: string[] }) =>
    (await apiClient.post<DemoModelResponse>('/model-export/demo-model', data)).data,

  // 浏览器下载 PMML/ONNX
  downloadExported: (resp: ModelExportResponse): void => {
    const bytes = Uint8Array.from(atob(resp.content_b64), (c) => c.charCodeAt(0));
    const blob = new Blob([bytes], { type: resp.mime_type });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', resp.filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};