/** 合同 API — Phase 4 B21. */
import { apiClient } from './client';

export interface Contract {
  contract_id: string;
  tenant_id: string;
  contract_number: string;
  contract_type: string;
  status: string;
  valid_from: string;
  valid_until: string;
  signed_at: string | null;
}

export const contractsApi = {
  listTemplates: async () =>
    (await apiClient.get<{ items: unknown[]; total: number }>('/templates')).data,

  list: async () =>
    (await apiClient.get<{ items: Contract[]; total: number }>('')).data,

  apply: async (data: {
    contract_type: string;
    valid_from: string;
    valid_until: string;
  }) =>
    (await apiClient.post<Contract>('', data)).data,

  get: async (id: string) =>
    (await apiClient.get<Contract>(`/${id}`)).data,

  sign: async (id: string, data: { signature: string }) =>
    (await apiClient.post<Contract>(`/${id}/sign`, data)).data,

  applyVatInvoice: async (_id: string, data: { invoice_type: string }) =>
    (await apiClient.post('/vat-invoice', data)).data,
};