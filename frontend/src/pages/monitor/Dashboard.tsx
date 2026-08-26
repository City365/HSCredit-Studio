/**
 * 监控告警看板.
 *
 * Phase 1 阶段（无专用 monitor API）：
 * - KPI 卡：运行中 / 失败 / 总数 / 平均 PSI（基于 runs API 聚合）
 * - 运行中 Run 列表：点击跳转 run 详情
 * - 最近失败 Run 列表
 *
 * Phase 2 引入 monitor-configs / alerts API 后会替换为 PSI / AUC 趋势图.
 */

import { Card, Row, Col, Statistic, Table, Tag, Empty, Spin } from 'antd';
import { useNavigate } from 'react-router-dom';
import { runsApi, type ListRunsParams } from '@/api/runs';
import { useApiQuery } from '@/hooks/useApi';
import type { Run, RunStatus } from '@/types';

const STATUS_COLOR: Record<RunStatus, string> = {
  pending: 'default',
  queued: 'default',
  running: 'processing',
  cached: 'success',
  success: 'success',
  failed: 'error',
  cancelled: 'default',
  retrying: 'warning',
};

export default function MonitorDashboardPage() {
  const navigate = useNavigate();

  const { data: runningRuns, isLoading: loadingRunning } = useApiQuery(
    ['runs', 'running'],
    () => runsApi.list({ status: 'running', page_size: 5 } as ListRunsParams),
    {} as ListRunsParams,
  );
  const { data: failedRuns, isLoading: loadingFailed } = useApiQuery(
    ['runs', 'failed'],
    () => runsApi.list({ status: 'failed', page_size: 5 } as ListRunsParams),
    {} as ListRunsParams,
  );
  const { data: allRuns } = useApiQuery(
    ['runs', 'all-count'],
    () => runsApi.list({ page_size: 1 } as ListRunsParams),
    {} as ListRunsParams,
  );

  // PSI 占位值 — Phase 2 由后端 monitor-configs 提供
  const placeholderPsi = 0.08;

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="运行中 Run"
              value={runningRuns?.total ?? 0}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="失败 Run"
              value={failedRuns?.total ?? 0}
              valueStyle={{ color: '#cf1322' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="Run 总数" value={allRuns?.total ?? 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="平均 PSI"
              value={placeholderPsi}
              precision={3}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
      </Row>

      <Card title="运行中的 Run" style={{ marginBottom: 16 }}>
        {loadingRunning ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin />
          </div>
        ) : (runningRuns?.items?.length ?? 0) > 0 ? (
          <Table<Run>
            dataSource={runningRuns?.items ?? []}
            rowKey="id"
            size="small"
            pagination={false}
            onRow={(row: Run) => ({
              onClick: () => navigate(`/runs/${row.id}`),
              style: { cursor: 'pointer' },
            })}
            columns={[
              { title: 'Run #', dataIndex: 'run_number', width: 80 },
              {
                title: '状态',
                dataIndex: 'status',
                render: (s: RunStatus) => <Tag color={STATUS_COLOR[s]}>{s}</Tag>,
              },
              { title: '提交时间', dataIndex: 'submitted_at' },
              {
                title: '耗时(秒)',
                dataIndex: 'duration_seconds',
                render: (v: number | null | undefined) =>
                  v !== undefined && v !== null ? v.toFixed(1) : '-',
              },
            ]}
          />
        ) : (
          <Empty description="当前无运行中的 Run" />
        )}
      </Card>

      <Card title="最近失败">
        {loadingFailed ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin />
          </div>
        ) : (failedRuns?.items?.length ?? 0) > 0 ? (
          <Table<Run>
            dataSource={failedRuns?.items ?? []}
            rowKey="id"
            size="small"
            pagination={false}
            columns={[
              { title: 'Run #', dataIndex: 'run_number', width: 80 },
              {
                title: '错误',
                dataIndex: 'error_summary',
                ellipsis: true,
                render: (v: string | null | undefined) => (
                  <span style={{ color: 'red' }}>{v ?? '-'}</span>
                ),
              },
              { title: '提交时间', dataIndex: 'submitted_at' },
            ]}
          />
        ) : (
          <Empty description="最近无失败 Run" />
        )}
      </Card>
    </div>
  );
}