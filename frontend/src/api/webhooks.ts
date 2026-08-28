/** Webhooks API 客户端 — Phase 8 B35.

API 列表 (10 端点):
- GET    /webhooks/events
- GET    /webhooks/subscriptions
- POST   /webhooks/subscriptions
- GET    /webhooks/subscriptions/{id}
- PATCH  /webhooks/subscriptions/{id}
- DELETE /webhooks/subscriptions/{id}
- POST   /webhooks/subscriptions/{id}/test
- GET    /webhooks/subscriptions/{id}/deliveries
- POST   /webhooks/deliveries/{id}/retry
- POST   /webhooks/publish
- POST   /webhooks/verify-signature
*/
import { apiClient } from './client';

export interface WebhookSubscription {
  subscription_id: string;
  tenant_id: string;
  url: string;
  events: string[];
  active: boolean;
  description: string;
  created_at: string;
}

export interface WebhookSubscriptionWithSecret extends WebhookSubscription {
  secret?: string;
}

export interface WebhookEvent {
  event: string;
  category: string;
  description: string;
}

export interface WebhookDelivery {
  delivery_id: string;
  subscription_id: string;
  event: string;
  status: 'pending' | 'success' | 'failed' | 'retrying' | 'cancelled';
  attempt: number;
  response_status: number | null;
  last_error: string | null;
  scheduled_at: string;
  delivered_at: string | null;
  created_at: string;
}

export interface WebhookTestResult {
  success: boolean;
  response_status: number | null;
  error: string | null;
  secret_used: string;
  delivery_id: string;
}

export const webhooksApi = {
  listEvents: async () =>
    (await apiClient.get<{ events: WebhookEvent[]; total: number }>('/webhooks/events')).data,

  listSubscriptions: async () =>
    (await apiClient.get<{ items: WebhookSubscription[]; total: number }>('/webhooks/subscriptions')).data,

  createSubscription: async (data: {
    url: string;
    events: string[];
    active?: boolean;
    description?: string;
  }) =>
    (await apiClient.post<WebhookSubscriptionWithSecret>(
      '/webhooks/subscriptions',
      data,
    )).data,

  getSubscription: async (id: string) =>
    (await apiClient.get<WebhookSubscription>(`/webhooks/subscriptions/${id}`)).data,

  updateSubscription: async (id: string, data: Partial<{
    url: string;
    events: string[];
    active: boolean;
    description: string;
  }>) =>
    (await apiClient.patch<WebhookSubscription>(`/webhooks/subscriptions/${id}`, data)).data,

  deleteSubscription: async (id: string) => {
    await apiClient.delete<void>(`/webhooks/subscriptions/${id}`);
  },

  testSubscription: async (id: string) =>
    (await apiClient.post<WebhookTestResult>(`/webhooks/subscriptions/${id}/test`)).data,

  listDeliveries: async (id: string) =>
    (await apiClient.get<{ items: WebhookDelivery[]; total: number }>(
      `/webhooks/subscriptions/${id}/deliveries`,
    )).data,

  retryDelivery: async (deliveryId: string) =>
    (await apiClient.post<WebhookDelivery>(`/webhooks/deliveries/${deliveryId}/retry`)).data,

  publishEvent: async (event: string, payload: Record<string, unknown>) =>
    (await apiClient.post<{
      event_id: string;
      event: string;
      tenant_id: string;
      enqueued_count: number;
      published_at: string;
    }>('/webhooks/publish', { event, payload })).data,

  verifySignature: async (data: {
    secret: string;
    payload: string;
    signature: string;
    timestamp: number;
  }) =>
    (await apiClient.post<{ valid: boolean; reason?: string }>(
      '/webhooks/verify-signature',
      data,
    )).data,
};