/**
 * 监控告警看板.
 *
 * Phase 2 批次 11 — 实时监控大屏:
 * - KPI 卡片: 运行中 / 失败 / Run 总数 / 节点成功率 / Workflow / Artifact
 * - Run 24h 趋势折线图 (按小时聚合)
 * - Top 失败原因 (按错误码)
 * - 节点吞吐 (按节点类型, 展示 avg / p95 耗时)
 * - 活跃告警 (KPI 阈值违规)
 * - 运行中 Run 列表 / 最近失败 Run 列表
 */

import { useMemo } from 'react';
import {
  Card,
  Row,
  Col,
  Statistic,
  Table,
  Tag,
  Empty,
  Spin,
  Typography,
  Space,
  Progress,
  Alert,
} from 'antd';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ClockCircleOutlined,
  RocketOutlined,
  ThunderboltOutlined,
  DatabaseOutlined,
  WarningOutlined,
  AlertOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import { runsApi, type ListRunsParams } from '@/api/runs';
import { monitorApi, type NodeThroughput, type TopFailure } from '@/api/monitor';
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

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${units[i]}`;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

export default function MonitorDashboardPage() {
  const navigate = useNavigate();

  const overviewQuery = useQuery({
    queryKey: ['monitor', 'overview'],
    queryFn: () => monitorApi.overview(),
    refetchInterval: 30_000,
  });

  const timeseriesQuery = useQuery({
    queryKey: ['monitor', 'runs', 'timeseries'],
    queryFn: () => monitorApi.runsTimeseries(24),
    refetchInterval: 60_000,
  });

  const failuresQuery = useQuery({
    queryKey: ['monitor', 'top-failures'],
    queryFn: () => monitorApi.topFailures(24, 5),
    refetchInterval: 60_000,
  });

  const throughputQuery = useQuery({
    queryKey: ['monitor', 'nodes', 'throughput'],
    queryFn: () => monitorApi.nodesThroughput(24),
    refetchInterval: 60_000,
  });

  const alertsQuery = useQuery({
    queryKey: ['monitor', 'alerts'],
    queryFn: () => monitorApi.alerts(),
    refetchInterval: 30_000,
  });

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

  const overview = overviewQuery.data;
  const timeseries = timeseriesQuery.data;
  const failures: TopFailure[] = failuresQuery.data?.failures ?? [];
  const throughput: NodeThroughput[] = throughputQuery.data?.nodes ?? [];
  const alerts = alertsQuery.data?.alerts ?? [];

  // 趋势 SVG 折线图 (纯 SVG 渲染, 不引入图表库)
  const trendSvg = useMemo(() => {
    const buckets = timeseries?.buckets ?? [];
    if (buckets.length === 0) return null;
    const maxVal = Math.max(...buckets.map((b) => b.total), 1);
    const w = 600;
    const h = 120;
    const stepX = buckets.length > 1 ? w / (buckets.length - 1) : 0;

    const pathTotal = buckets
      .map((b, i) => `${i === 0 ? 'M' : 'L'} ${i * stepX} ${h - (b.total / maxVal) * h}`)
      .join(' ');
    const pathSuccess = buckets
      .map((b, i) => `${i === 0 ? 'M' : 'L'} ${i * stepX} ${h - (b.success / maxVal) * h}`)
      .join(' ');
    const pathFailed = buckets
      .map((b, i) => `${i === 0 ? 'M' : 'L'} ${i * stepX} ${h - (b.failed / maxVal) * h}`)
      .join(' ');

    return { pathTotal, pathSuccess, pathFailed, w, h, buckets };
  }, [timeseries]);

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        <RocketOutlined /> 监控告警看板
      </Typography.Title>
      <Typography.Paragraph type="secondary">
        租户运营实时监控 — Run / Node / Workflow / Artifact 指标 + 趋势图 + 告警
      </Typography.Paragraph>

      {/* 活跃告警 */}
      {alerts.length > 0 && (
        <Card style={{ marginBottom: 16, borderColor: '#ff4d4f' }}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Text strong>
              <AlertOutlined style={{ color: '#ff4d4f' }} /> 活跃告警 ({alerts.length})
            </Typography.Text>
            {alerts.map((a) => (
              <Alert
                key={a.code}
                type={a.severity === 'critical' ? 'error' : 'warning'}
                showIcon
                message={a.code}
                description={a.message}
              />
            ))}
          </Space>
        </Card>
      )}

      {/* KPI 卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Card>
            <Statistic
              title="运行中 Run"
              value={overview?.run_active ?? 0}
              prefix={<RocketOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic
              title="失败 Run (24h)"
              value={overview?.run_failed_24h ?? 0}
              prefix={<WarningOutlined />}
              valueStyle={{ color: '#cf1322' }}
            />
            <Progress
              percent={Math.round((overview?.run_success_rate_24h ?? 0) * 100)}
              size="small"
              strokeColor={
                (overview?.run_success_rate_24h ?? 0) > 0.9
                  ? '#52c41a'
                  : (overview?.run_success_rate_24h ?? 0) > 0.7
                    ? '#faad14'
                    : '#ff4d4f'
              }
              format={(p) => `${p}% 成功率`}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic
              title="节点成功率"
              value={(overview?.node_success_rate ?? 0) * 100}
              precision={1}
              suffix="%"
              prefix={<CheckCircleOutlined />}
              valueStyle={{
                color: (overview?.node_success_rate ?? 0) > 0.9 ? '#52c41a' : '#faad14',
              }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic
              title="Workflow / 版本"
              value={overview?.workflow_total ?? 0}
              suffix={
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  / {overview?.workflow_version_total ?? 0} 版本
                </Typography.Text>
              }
              prefix={<DatabaseOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic
              title="Artifact 数 / 大小"
              value={overview?.artifact_total ?? 0}
              suffix={
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  / {formatBytes(overview?.artifact_size_bytes ?? 0)}
                </Typography.Text>
              }
              prefix={<DatabaseOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic
              title="平均 Run 耗时"
              value={overview?.avg_run_duration_seconds ?? 0}
              precision={1}
              suffix="s"
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* 24h Run 趋势图 */}
      <Card title={<><ClockCircleOutlined /> Run 提交趋势 (24h)</>} style={{ marginBottom: 16 }}>
        {trendSvg ? (
          <div style={{ overflowX: 'auto' }}>
            <svg width={trendSvg.w} height={trendSvg.h} viewBox={`0 0 ${trendSvg.w} ${trendSvg.h}`}>
              {/* 网格 */}
              {[0, 0.25, 0.5, 0.75, 1].map((p) => (
                <line
                  key={p}
                  x1={0}
                  y1={trendSvg.h * (1 - p)}
                  x2={trendSvg.w}
                  y2={trendSvg.h * (1 - p)}
                  stroke="#f0f0f0"
                  strokeWidth={1}
                />
              ))}
              <path d={trendSvg.pathTotal} fill="none" stroke="#1677ff" strokeWidth={2} />
              <path d={trendSvg.pathSuccess} fill="none" stroke="#52c41a" strokeWidth={1.5} />
              <path d={trendSvg.pathFailed} fill="none" stroke="#ff4d4f" strokeWidth={1.5} />
            </svg>
            <Space style={{ marginTop: 8 }}>
              <Tag color="blue">● 总提交 ({trendSvg.buckets.reduce((a, b) => a + b.total, 0)})</Tag>
              <Tag color="green">● 成功 ({trendSvg.buckets.reduce((a, b) => a + b.success, 0)})</Tag>
              <Tag color="red">● 失败 ({trendSvg.buckets.reduce((a, b) => a + b.failed, 0)})</Tag>
            </Space>
          </div>
        ) : (
          <Spin />
        )}
      </Card>

      <Row gutter={16}>
        {/* Top 失败 */}
        <Col span={12}>
          <Card title={<><WarningOutlined /> Top 失败原因 (24h)</>} style={{ marginBottom: 16 }}>
            {failures.length > 0 ? (
              <Table<NodeThroughput | TopFailure>
                size="small"
                dataSource={failures as unknown as NodeThroughput[]}
                rowKey="code"
                pagination={false}
                columns={[
                  { title: '错误码', dataIndex: 'code', width: 200 },
                  {
                    title: '消息',
                    dataIndex: 'message',
                    ellipsis: true,
                    render: (v: string) => (
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {v || '—'}
                      </Typography.Text>
                    ),
                  },
                  {
                    title: '次数',
                    dataIndex: 'count',
                    width: 80,
                    render: (v: number) => <Tag color="red">{v}</Tag>,
                  },
                ]}
              />
            ) : (
              <Empty description="最近 24h 无失败 🎉" />
            )}
          </Card>
        </Col>

        {/* 节点吞吐 */}
        <Col span={12}>
          <Card title={<><ThunderboltOutlined /> 节点吞吐 (24h)</>} style={{ marginBottom: 16 }}>
            {throughput.length > 0 ? (
              <Table<NodeThroughput>
                size="small"
                dataSource={throughput}
                rowKey="node_type"
                pagination={false}
                columns={[
                  { title: '节点类型', dataIndex: 'node_type', width: 160 },
                  {
                    title: '调用次数',
                    dataIndex: 'count',
                    width: 100,
                    render: (v: number, r) => (
                      <Space>
                        <span>{v}</span>
                        <Tag color="green">{r.success_count}</Tag>
                      </Space>
                    ),
                  },
                  {
                    title: '成功率',
                    dataIndex: 'success_rate',
                    width: 100,
                    render: (v: number) => `${(v * 100).toFixed(0)}%`,
                  },
                  {
                    title: '平均 / p95',
                    key: 'dur',
                    render: (_: unknown, r) => (
                      <Typography.Text style={{ fontFamily: 'monospace', fontSize: 12 }}>
                        {formatDuration(r.avg_duration_seconds)} / {formatDuration(r.p95_duration_seconds)}
                      </Typography.Text>
                    ),
                  },
                ]}
              />
            ) : (
              <Spin />
            )}
          </Card>
        </Col>
      </Row>

      {/* 运行中 + 失败 Run 列表 */}
      <Row gutter={16}>
        <Col span={12}>
          <Card title="运行中的 Run" style={{ marginBottom: 16 }}>
            {loadingRunning ? (
              <Spin />
            ) : (runningRuns?.items?.length ?? 0) > 0 ? (
              <Table<Run>
                size="small"
                dataSource={runningRuns?.items ?? []}
                rowKey="id"
                pagination={false}
                onRow={(row) => ({
                  onClick: () => navigate(`/runs/${row.id}`),
                  style: { cursor: 'pointer' },
                })}
                columns={[
                  { title: 'Run #', dataIndex: 'run_number', width: 70 },
                  {
                    title: '状态',
                    dataIndex: 'status',
                    render: (s: RunStatus) => <Tag color={STATUS_COLOR[s]}>{s}</Tag>,
                  },
                  {
                    title: '耗时',
                    dataIndex: 'duration_seconds',
                    render: (v: number | null | undefined) =>
                      v !== undefined && v !== null ? formatDuration(v) : '-',
                  },
                ]}
              />
            ) : (
              <Empty description="无运行中 Run" />
            )}
          </Card>
        </Col>
        <Col span={12}>
          <Card title="最近失败 Run">
            {loadingFailed ? (
              <Spin />
            ) : (failedRuns?.items?.length ?? 0) > 0 ? (
              <Table<Run>
                size="small"
                dataSource={failedRuns?.items ?? []}
                rowKey="id"
                pagination={false}
                onRow={(row) => ({
                  onClick: () => navigate(`/runs/${row.id}`),
                  style: { cursor: 'pointer' },
                })}
                columns={[
                  { title: 'Run #', dataIndex: 'run_number', width: 70 },
                  {
                    title: '错误',
                    dataIndex: 'error_summary',
                    ellipsis: true,
                    render: (v: string | null | undefined) => (
                      <span style={{ color: '#cf1322', fontSize: 12 }}>{v ?? '-'}</span>
                    ),
                  },
                  { title: '提交时间', dataIndex: 'submitted_at' },
                ]}
              />
            ) : (
              <Empty description="最近无失败 Run 🎉" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}