/**
 * 模型仓库 — Phase 1 阶段从「成功的 Run」聚合展示可部署模型.
 *
 * Phase 1 没有专用 models API（Phase 2 引入）；
 * 当前实现：从 runsApi 拉取 status=success 的 Run 作为「模型候选」，
 * 列表显示 Run # / 工作流 / 提交时间 / 耗时 / 指标 / 状态 / 操作（详情 / 部署占位）.
 */

import { Table, Tag, Button, Space, Empty, Spin } from 'antd';
import { useNavigate } from 'react-router-dom';
import { runsApi, type ListRunsParams } from '@/api/runs';
import { useApiQuery } from '@/hooks/useApi';
import type { Run } from '@/types';

interface ModelCandidateColumn {
  title: string;
  dataIndex?: string;
  key: string;
  width?: number;
  ellipsis?: boolean;
  render?: (value: unknown, row: Run) => React.ReactNode;
}

export default function ModelRepositoryPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useApiQuery(
    ['models', 'successful-runs'],
    () => runsApi.list({ status: 'success', page_size: 50 } as ListRunsParams),
    {} as ListRunsParams,
  );

  const columns: ModelCandidateColumn[] = [
    { title: 'Run #', dataIndex: 'run_number', key: 'run_number', width: 80 },
    { title: '工作流 ID', dataIndex: 'workflow_id', key: 'workflow_id', ellipsis: true },
    { title: '提交时间', dataIndex: 'submitted_at', key: 'submitted_at' },
    {
      title: '耗时(秒)',
      dataIndex: 'duration_seconds',
      key: 'duration',
      width: 110,
      render: (v: unknown) =>
        typeof v === 'number' ? v.toFixed(1) : '-',
    },
    {
      title: '指标',
      dataIndex: 'metrics',
      key: 'metrics',
      render: (m: unknown) => {
        if (!m || typeof m !== 'object') return '-';
        const entries = Object.entries(m as Record<string, unknown>).slice(0, 3);
        if (entries.length === 0) return '-';
        return (
          <Space size={4}>
            {entries.map(([k, v]) => (
              <Tag key={k}>
                {k}: {String(v)}
              </Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: unknown) => <Tag color="green">{String(s)}</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_: unknown, row: Run) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/runs/${row.id}`)}>
            详情
          </Button>
          <Button size="small" type="primary">
            部署
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <h3 style={{ marginBottom: 16 }}>已成功训练的模型（基于成功 Run）</h3>
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin />
        </div>
      ) : (data?.items?.length ?? 0) > 0 ? (
        <Table<Run>
          columns={columns as never}
          dataSource={data?.items ?? []}
          loading={isLoading}
          rowKey="id"
          pagination={{ pageSize: 20 }}
        />
      ) : (
        <Empty description="暂无可用模型（Phase 2 引入专用 models API）" />
      )}
    </div>
  );
}