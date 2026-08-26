/**
 * Run 列表 — 展示历史运行.
 *
 * 状态颜色映射见 STATUS_COLOR
 */

import { useState } from 'react';
import { Table, Tag, Button, Input, Space } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { runsApi } from '@/api/runs';
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

export default function RunListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<RunStatus | undefined>(undefined);

  const { data, isLoading } = useApiQuery(['runs'], runsApi.list, {
    page,
    page_size: 20,
    status: statusFilter,
  });

  const columns = [
    { title: 'Run #', dataIndex: 'run_number', key: 'run_number', width: 80 },
    {
      title: '工作流',
      dataIndex: 'workflow_id',
      key: 'workflow_id',
      ellipsis: true,
      render: (v: string) => (
        <a onClick={() => navigate(`/workflows/${v}`)}>{v.slice(0, 8)}</a>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (s: RunStatus) => <Tag color={STATUS_COLOR[s]}>{s}</Tag>,
    },
    { title: '提交时间', dataIndex: 'submitted_at', key: 'submitted_at', width: 180 },
    {
      title: '耗时(秒)',
      dataIndex: 'duration_seconds',
      key: 'duration',
      render: (v: number | null | undefined) => (v != null ? v.toFixed(1) : '-'),
    },
    {
      title: '错误',
      dataIndex: 'error_summary',
      key: 'error',
      ellipsis: true,
      render: (v: string | null | undefined) =>
        v ? <span style={{ color: 'red' }}>{v}</span> : '-',
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: unknown, row: Run) => (
        <Button size="small" onClick={() => navigate(`/runs/${row.id}`)}>
          详情
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Input.Search
          placeholder="按状态筛选"
          allowClear
          onSearch={(v) => {
            const next = v ? (v as RunStatus) : undefined;
            setStatusFilter(next);
            setPage(1);
          }}
          style={{ width: 220 }}
        />
      </Space>
      <Table
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        rowKey="id"
        pagination={{
          current: page,
          pageSize: 20,
          total: data?.total ?? 0,
          onChange: setPage,
          showSizeChanger: false,
        }}
        scroll={{ x: 'max-content' }}
      />
      <div style={{ display: 'none' }}>{t('runs.title', '运行历史')}</div>
    </div>
  );
}
