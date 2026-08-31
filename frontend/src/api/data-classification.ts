/** 数据脱敏 API — Phase 5 B24. */
import { apiClient } from './client';

export interface FieldClassification {
  field_name: string;
  level: 'public' | 'internal' | 'sensitive' | 'high_sensitive';
  pattern: string;
}

export const dataClassificationApi = {
  listFields: async () =>
    (await apiClient.get<{ items: FieldClassification[]; total: number }>('/data-classification/fields')).data,

  redact: async (data: { payload: Record<string, unknown>; fields?: string[] }) =>
    (await apiClient.post<{
      redacted: Record<string, string>;
      masked_fields: string[];
    }>('/redact', data)).data,

  hashField: async (data: { value: string; field: string }) =>
    (await apiClient.post<{ field: string; hash: string; masked: string }>(
      '/hash',
      data,
    )).data,
};