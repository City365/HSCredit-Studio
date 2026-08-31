/** PIPL 数据保护 API — Phase 5 B26. */
import { apiClient } from './client';

export interface ConsentRecord {
  consent_id: string;
  user_id: string;
  purpose: string;
  granted: boolean;
  granted_at: string;
  revoked_at: string | null;
}

export interface DsrItem {
  request_id: string;
  user_id: string;
  request_type: 'query' | 'delete' | 'correct' | 'portability';
  status: 'pending' | 'processing' | 'completed' | 'rejected';
  reason: string;
  submitted_at: string;
  due_at: string;
  completed_at: string | null;
}

export interface CrossBorderTransfer {
  transfer_id: string;
  tenant_id: string;
  destination_country: string;
  recipient: string;
  legal_basis: string;
  approved: boolean;
  created_at: string;
}

export const piplApi = {
  listMyConsents: async () =>
    (await apiClient.get<{ items: ConsentRecord[]; total: number }>('/consent')).data,

  grantConsent: async (data: { purpose: string }) =>
    (await apiClient.post<ConsentRecord>('/consents/grant', data)).data,

  revokeConsent: async (data: { purpose: string }) =>
    (await apiClient.post('/consents/revoke', data)).data,

  checkConsent: async (params: { purpose: string }) =>
    (await apiClient.get<{ granted: boolean }>('/consents/check', { params })).data,

  listMyDsrs: async () =>
    (await apiClient.get<{ items: DsrItem[]; total: number }>('/dsr')).data,

  submitDsr: async (data: {
    request_type: 'query' | 'delete' | 'correct' | 'portability';
    reason: string;
  }) => (await apiClient.post<DsrItem>('/dsr', data)).data,

  exportMyData: async () =>
    (await apiClient.post<{ download_url: string; size_bytes: number }>('/dsr/portability', {})).data,

  anonymizeMyData: async () =>
    (await apiClient.post<{ affected_fields: string[] }>('/dsr/anonymize', {})).data,

  listCrossBorder: async () =>
    (await apiClient.get<{ items: CrossBorderTransfer[]; total: number }>(
      '/cross-border',
    )).data,

  applyCrossBorder: async (data: {
    destination_country: string;
    recipient: string;
    legal_basis: string;
  }) => (await apiClient.post<CrossBorderTransfer>('/cross-border', data)).data,

  getCurrentPolicy: async () =>
    (await apiClient.get<{ version: string; content_md: string; updated_at: string }>(
      '/policy',
    )).data,
};