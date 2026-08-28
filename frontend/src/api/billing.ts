/** 计费 API — Phase 4 B20. */
import { apiClient } from './client';

export interface Bill {
  bill_id: string;
  tenant_id: string;
  billing_period: string;
  plan: string;
  status: string;
  base_fee: number;
  overage_runs_fee: number;
  overage_duration_fee: number;
  overage_storage_fee: number;
  total_amount: number;
  currency: string;
  due_date: string;
  paid_at: string | null;
  payment_channel: string | null;
}

export const billingApi = {
  list: async () =>
    (await apiClient.get<{ items: Bill[]; total: number }>('')).data,

  generate: async (data: { billing_period: string }) =>
    (await apiClient.post<Bill>('', data)).data,

  get: async (id: string) =>
    (await apiClient.get<Bill>(`/${id}`)).data,

  issueInvoice: async (id: string) =>
    (await apiClient.post<{
      invoice_id: string;
      invoice_number: string;
      pdf_path: string;
      amount: number;
    }>(`/${id}/invoice`)).data,

  createPaymentLink: async (id: string, data: { channel: string }) =>
    (await apiClient.post<{
      payment_url: string;
      amount: number;
      channel: string;
      expires_at: string;
    }>(`/${id}/payment-link`, data)).data,

  exportReconciliation: async (params?: { from_period?: string; to_period?: string }) =>
    (await apiClient.get('/reconciliation/export', { params, responseType: 'blob' })).data,
};