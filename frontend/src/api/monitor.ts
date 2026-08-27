/**
 * 监控 API — 运营 Dashboard 数据.
 *
 * 对应后端 /api/v1/{tenant}/monitor/* 端点.
 */

import { apiClient } from './client';

export interface MonitorOverview {
  run_total: number;
  run_active: number;
  run_24h: number;
  run_7d: number;
  run_success_24h: number;
  run_failed_24h: number;
  run_success_rate_24h: number;
  node_total: number;
  node_success_rate: number;
  workflow_total: number;
  workflow_version_total: number;
  artifact_total: number;
  artifact_size_bytes: number;
  avg_run_duration_seconds: number;
  as_of: string;
}

export interface RunTimeseriesBucket {
  timestamp: string;
  total: number;
  success: number;
  failed: number;
}

export interface TopFailure {
  code: string;
  message: string;
  count: number;
  last_seen: string | null;
}

export interface NodeThroughput {
  node_type: string;
  count: number;
  success_count: number;
  success_rate: number;
  avg_duration_seconds: number;
  p95_duration_seconds: number;
  max_duration_seconds: number;
}

export interface Alert {
  severity: 'critical' | 'warning' | 'info';
  code: string;
  message: string;
  metric_value: number;
  threshold: number;
  as_of: string;
}

export const monitorApi = {
  overview: async (): Promise<MonitorOverview> => {
    const resp = await apiClient.get<MonitorOverview>('/monitor/overview');
    return resp.data;
  },

  runsTimeseries: async (hours = 24): Promise<{ buckets: RunTimeseriesBucket[] }> => {
    const resp = await apiClient.get<{ hours: number; buckets: RunTimeseriesBucket[] }>(
      '/monitor/runs/timeseries',
      { params: { hours } },
    );
    return resp.data;
  },

  topFailures: async (hours = 24, limit = 10): Promise<{ failures: TopFailure[] }> => {
    const resp = await apiClient.get<{ hours: number; failures: TopFailure[] }>(
      '/monitor/top-failures',
      { params: { hours, limit } },
    );
    return resp.data;
  },

  nodesThroughput: async (hours = 24): Promise<{ nodes: NodeThroughput[] }> => {
    const resp = await apiClient.get<{ hours: number; nodes: NodeThroughput[] }>(
      '/monitor/nodes/throughput',
      { params: { hours } },
    );
    return resp.data;
  },

  alerts: async (): Promise<{ alert_count: number; alerts: Alert[] }> => {
    const resp = await apiClient.get<{ alert_count: number; alerts: Alert[] }>(
      '/monitor/alerts',
    );
    return resp.data;
  },
};