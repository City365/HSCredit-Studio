/**
 * 审计日志页面 — 运营 / 合规审计.
 *
 * 功能:
 * - 顶部 KPI 卡片 (总事件/24h/7d/活跃用户/Top 动作)
 * - 过滤: 用户/动作/资源类型/时间区间
 * - 列表: 时间/操作者/动作/资源类型/资源 ID/IP/UA
 * - 导出 CSV
 */
import { useState, useMemo } from 'react';
import {
  Card,
  Row,
  Col,
  Statistic,
  Table,
  Tag,
  Space,
  Typography,
  Input,
  Select,
  DatePicker,
  Button,
  message as antdMessage,
  Tooltip,
} from 'antd';
import {
  ReloadOutlined,
  DownloadOutlined,
  UserOutlined,
  AuditOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import { useQuery } from '@tanstack/react-query';
import { auditApi, type AuditEvent, type AuditStats } from '@/api/audit';

const { RangePicker } = DatePicker;

const ACTION_COLORS: Record<string, string> = {
  login: 'green',
  login_failed: 'red',
  logout: 'default',
  workflow_create: 'blue',
  workflow_update: 'cyan',
  workflow_delete: 'volcano',
  workflow_run_submit: 'geekblue',
  workflow_run_cancel: 'orange',
  workflow_run_retry_node: 'purple',
  template_instantiate: 'magenta',
  user_create: 'lime',
  user_delete: 'red',
};

export default function AuditPage() {
  const [filters, setFilters] = useState<{
    user_id?: string;
    action?: string;
    resource_type?: string;
    range?: [Dayjs, Dayjs];
    page: number;
    page_size: number;
  }>({ page: 1, page_size: 50 });

  // 统计
  const statsQuery = useQuery({
    queryKey: ['audit', 'stats'],
    queryFn: () => auditApi.stats(),
    refetchInterval: 60_000,
  });

  // 事件列表
  const eventsQuery = useQuery({
    queryKey: ['audit', 'events', filters],
    queryFn: () =>
      auditApi.list({
        user_id: filters.user_id,
        action: filters.action,
        resource_type: filters.resource_type,
        since: filters.range?.[0]?.toISOString(),
        until: filters.range?.[1]?.toISOString(),
        page: filters.page,
        page_size: filters.page_size,
      }),
    refetchInterval: 30_000,
  });

  const stats: AuditStats | undefined = statsQuery.data;
  const events: AuditEvent[] = eventsQuery.data?.items ?? [];
  const total = eventsQuery.data?.total ?? 0;

  const exportCsv = async () => {
    try {
      const blob = await auditApi.exportCsv({
        since: filters.range?.[0]?.toISOString(),
        until: filters.range?.[1]?.toISOString(),
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_events_${dayjs().format('YYYYMMDD_HHmmss')}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      antdMessage.success('审计日志导出完成');
    } catch (e) {
      antdMessage.error(`导出失败：${(e as Error).message}`);
    }
  };

  const columns = useMemo(
    () => [
      {
        title: '时间',
        dataIndex: 'occurred_at',
        key: 'occurred_at',
        width: 180,
        render: (v: string) => (
          <Typography.Text style={{ fontFamily: 'monospace', fontSize: 12 }}>
            {dayjs(v).format('YYYY-MM-DD HH:mm:ss')}
          </Typography.Text>
        ),
      },
      {
        title: '操作者',
        dataIndex: 'user_id',
        key: 'user_id',
        width: 220,
        render: (v: string | null) =>
          v ? (
            <Tooltip title={v}>
              <Tag icon={<UserOutlined />} color="blue">
                {v.slice(0, 8)}...
              </Tag>
            </Tooltip>
          ) : (
            <Tag>系统</Tag>
          ),
      },
      {
        title: '动作',
        dataIndex: 'action',
        key: 'action',
        width: 200,
        render: (v: string) => (
          <Tag color={ACTION_COLORS[v] || 'default'} style={{ fontFamily: 'monospace' }}>
            {v}
          </Tag>
        ),
      },
      {
        title: '资源类型',
        dataIndex: 'resource_type',
        key: 'resource_type',
        width: 120,
        render: (v: string | null) => (v ? <Tag>{v}</Tag> : '—'),
      },
      {
        title: '资源 ID',
        dataIndex: 'resource_id',
        key: 'resource_id',
        width: 160,
        render: (v: string | null) =>
          v ? (
            <Typography.Text style={{ fontFamily: 'monospace', fontSize: 12 }}>
              {v.slice(0, 8)}...
            </Typography.Text>
          ) : (
            '—'
          ),
      },
      {
        title: 'IP',
        dataIndex: 'ip_address',
        key: 'ip_address',
        width: 130,
        render: (v: string | null) => (v || '—'),
      },
      {
        title: '详情',
        dataIndex: 'details',
        key: 'details',
        ellipsis: true,
        render: (v: Record<string, unknown> | null) =>
          v ? (
            <Tooltip title={JSON.stringify(v, null, 2)}>
              <code style={{ fontSize: 12 }}>{JSON.stringify(v).slice(0, 80)}</code>
            </Tooltip>
          ) : (
            '—'
          ),
      },
    ],
    [],
  );

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        <AuditOutlined /> 审计日志
      </Typography.Title>
      <Typography.Paragraph type="secondary">
        合规审计追溯 — 所有用户登录、Run 提交、节点重试、模板实例化等关键操作记录。
      </Typography.Paragraph>

      {/* KPI 卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Card>
            <Statistic
              title="总事件数"
              value={stats?.total_events ?? 0}
              prefix={<AuditOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic
              title="活跃用户"
              value={stats?.unique_users ?? 0}
              prefix={<UserOutlined />}
              valueStyle={{ color: '#1677ff' }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic
              title="最近 24 小时"
              value={stats?.last_24h_events ?? 0}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic
              title="最近 7 天"
              value={stats?.last_7d_events ?? 0}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic
              title="不同动作"
              value={stats?.unique_actions ?? 0}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Top 动作
            </Typography.Text>
            <div style={{ marginTop: 8 }}>
              {stats?.by_action.slice(0, 3).map((a) => (
                <Tag
                  key={a.action}
                  color={ACTION_COLORS[a.action] || 'default'}
                  style={{ marginBottom: 2 }}
                >
                  {a.action}: {a.count}
                </Tag>
              ))}
            </div>
          </Card>
        </Col>
      </Row>

      {/* 过滤栏 */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap size="middle">
          <Input
            placeholder="用户 ID"
            allowClear
            style={{ width: 220 }}
            value={filters.user_id}
            onChange={(e) =>
              setFilters((f) => ({ ...f, user_id: e.target.value || undefined, page: 1 }))
            }
          />
          <Select
            placeholder="动作"
            allowClear
            style={{ width: 200 }}
            value={filters.action}
            onChange={(v) => setFilters((f) => ({ ...f, action: v, page: 1 }))}
            options={[
              { value: 'login', label: 'login' },
              { value: 'login_failed', label: 'login_failed' },
              { value: 'workflow_create', label: 'workflow_create' },
              { value: 'workflow_update', label: 'workflow_update' },
              { value: 'workflow_run_submit', label: 'workflow_run_submit' },
              { value: 'workflow_run_retry_node', label: 'workflow_run_retry_node' },
              { value: 'template_instantiate', label: 'template_instantiate' },
            ]}
          />
          <Select
            placeholder="资源类型"
            allowClear
            style={{ width: 160 }}
            value={filters.resource_type}
            onChange={(v) => setFilters((f) => ({ ...f, resource_type: v, page: 1 }))}
            options={[
              { value: 'workflow', label: 'workflow' },
              { value: 'run', label: 'run' },
              { value: 'node_execution', label: 'node_execution' },
              { value: 'template', label: 'template' },
              { value: 'user', label: 'user' },
            ]}
          />
          <RangePicker
            showTime
            onChange={(range) =>
              setFilters((f) => ({
                ...f,
                range: range as [Dayjs, Dayjs] | undefined,
                page: 1,
              }))
            }
          />
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              eventsQuery.refetch();
              statsQuery.refetch();
            }}
          >
            刷新
          </Button>
          <Button icon={<DownloadOutlined />} onClick={exportCsv}>
            导出 CSV
          </Button>
        </Space>
      </Card>

      {/* 列表 */}
      <Card>
        <Table
          rowKey="event_id"
          loading={eventsQuery.isLoading}
          dataSource={events}
          columns={columns}
          size="small"
          pagination={{
            current: filters.page,
            pageSize: filters.page_size,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (page, page_size) => setFilters((f) => ({ ...f, page, page_size })),
          }}
        />
      </Card>
    </div>
  );
}