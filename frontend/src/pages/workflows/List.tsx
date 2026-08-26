/**
 * 工作流列表 — 支持搜索 + 分页 + 删除.
 */

import { useState } from 'react';
import { Table, Button, Space, Input, Tag, Popconfirm, message } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { workflowsApi } from '@/api/workflows';
import { useApiQuery, useApiMutation } from '@/hooks/useApi';
import type { Workflow } from '@/types';

export default function WorkflowListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  const { data, isLoading } = useApiQuery(['workflows'], workflowsApi.list, {
    page,
    page_size: 20,
    search: search || undefined,
  });

  const deleteMutation = useApiMutation((id: string) => workflowsApi.delete(id), {
    onSuccess: () => {
      message.success(t('common.delete') + ' ✓');
      qc.invalidateQueries({ queryKey: ['workflows'] });
    },
    onError: (err: Error) => message.error(err.message),
  });

  const columns = [
    {
      title: t('workflow.name', '名称'),
      dataIndex: 'name',
      key: 'name',
      render: (text: string, row: Workflow) => (
        <a onClick={() => navigate(`/workflows/${row.id}`)}>{text}</a>
      ),
    },
    {
      title: t('workflow.description', '描述'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (v: string | null | undefined) => v ?? '-',
    },
    {
      title: t('workflow.tags', '标签'),
      dataIndex: 'tags',
      key: 'tags',
      render: (tags: string[]) =>
        tags && tags.length > 0 ? tags.map((tag) => <Tag key={tag}>{tag}</Tag>) : '-',
    },
    {
      title: t('workflow.currentVersion', '当前版本'),
      dataIndex: 'current_version_number',
      key: 'version',
      render: (v: number | null | undefined) => (v ? `v${v}` : '-'),
    },
    {
      title: t('workflow.lastRunStatus', '上次运行'),
      dataIndex: 'last_run_status',
      key: 'last_status',
      render: (s: string | null | undefined) => {
        if (!s) return '-';
        const color =
          s === 'success' ? 'green' : s === 'failed' ? 'red' : s === 'running' ? 'blue' : 'default';
        return <Tag color={color}>{s}</Tag>;
      },
    },
    {
      title: t('workflow.updatedAt', '更新时间'),
      dataIndex: 'updated_at',
      key: 'updated_at',
    },
    {
      title: t('common.actions', '操作'),
      key: 'actions',
      render: (_: unknown, row: Workflow) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/workflows/${row.id}`)}>
            {t('workflow.open', '打开')}
          </Button>
          <Popconfirm
            title={t('workflow.confirmDelete', '确认删除？')}
            onConfirm={() => deleteMutation.mutate(row.id)}
          >
            <Button size="small" icon={<DeleteOutlined />} danger />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Input.Search
          placeholder={t('workflow.search', '搜索工作流')}
          allowClear
          onSearch={(v) => {
            setSearch(v);
            setPage(1);
          }}
          style={{ width: 300 }}
        />
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => navigate('/workflows/new')}
        >
          {t('workflow.create', '新建')}
        </Button>
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
      />
    </div>
  );
}
