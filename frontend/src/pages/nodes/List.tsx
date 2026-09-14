/**
 * 节点管理主页 — Phase 6 B36.
 *
 * 表格: 节点类型/名称/分类/来源(系统/自定义)/状态/操作
 * 顶部: 同步系统节点 / 新增
 * 行操作: 详情/编辑元数据/编辑代码/试运行/删除
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined,
  CloudSyncOutlined,
  CodeOutlined,
  DeleteOutlined,
  EditOutlined,
  ExperimentOutlined,
  InfoCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
} from '@ant-design/icons';

import { customNodesApi } from '@/api/custom-nodes';
import { nodesApi } from '@/api/nodes';
import type { NodeToggleResponse } from '@/api/nodes';
import { useApiMutation, useApiQuery } from '@/hooks/useApi';
import { useAuthStore } from '@/stores/authStore';
import type {
  CustomNodeListItem,
  CustomNodeListResponse,
} from '@/api/custom-nodes';
import type { NodeDefinition } from '@/types';
import type { NodeMetaUpdate } from '@/api/nodes';

type SourceFilter = 'all' | 'system' | 'custom';
type StatusFilter = 'all' | 'enabled' | 'disabled';

export function NodesListPage(): React.ReactElement {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const role = useAuthStore((s) => s.role);

  const isAdmin = role === 'super_admin' || role === 'tenant_admin';

  // 过滤参数
  const [search, setSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [page, setPage] = useState(1);
  const pageSize = 20;

  // ===== 数据加载 =====
  // 系统节点 (NodeDefinition 列表)
  const enabledOnly = statusFilter === 'all' ? true : statusFilter === 'enabled';
  const sysQuery = useApiQuery<NodeDefinition[], { enabled_only: boolean }>(
    ['nodes', 'list'],
    () => nodesApi.list({ enabled_only: enabledOnly, include_contract: true }),
    { enabled_only: enabledOnly },
    { staleTime: 30_000 },
  );

  // 自定义节点
  const customQuery = useApiQuery<CustomNodeListResponse, { page: number; page_size: number; search: string }>(
    ['custom-nodes', 'list'],
    () => customNodesApi.list({ page, page_size: pageSize, search }),
    { page, page_size: pageSize, search },
    { staleTime: 30_000 },
  );

  // ===== 启停切换 =====
  const toggleMutation = useApiMutation<NodeToggleResponse, { nodeType: string; enabled: boolean }>(
    ({ nodeType, enabled }) =>
      enabled ? nodesApi.enable(nodeType) : nodesApi.disable(nodeType),
  );

  const handleToggle = async (node: NodeDefinition, enabled: boolean) => {
    try {
      await toggleMutation.mutateAsync({ nodeType: node.node_type, enabled });
      message.success(enabled ? `已启用 ${node.node_type}` : `已停用 ${node.node_type}`);
      void sysQuery.refetch();
    } catch (e) {
      message.error(`操作失败: ${(e as Error).message}`);
    }
  };

  // ===== 元数据编辑 Modal =====
  const [metaEdit, setMetaEdit] = useState<NodeDefinition | null>(null);
  const [metaForm] = Form.useForm<NodeMetaUpdate>();

  const openMetaEdit = (node: NodeDefinition) => {
    setMetaEdit(node);
    metaForm.setFieldsValue({
      name: node.name,
      description: node.description,
      icon: node.icon,
    });
  };

  const metaSaveMutation = useApiMutation<NodeDefinition, { nodeType: string; payload: NodeMetaUpdate }>(
    ({ nodeType, payload }) => nodesApi.updateMeta(nodeType, payload),
  );

  const handleMetaSave = async () => {
    if (!metaEdit) return;
    try {
      const values = await metaForm.validateFields();
      await metaSaveMutation.mutateAsync({ nodeType: metaEdit.node_type, payload: values });
      message.success('元数据已更新');
      setMetaEdit(null);
      void sysQuery.refetch();
    } catch (e) {
      if ((e as { errorFields?: unknown }).errorFields) return; // 表单校验
      message.error(`更新失败: ${(e as Error).message}`);
    }
  };

  // ===== 删除自定义节点 =====
  const deleteMutation = useApiMutation<void, string>((id) =>
    customNodesApi.delete(id),
  );

  const handleDelete = async (cn: CustomNodeListItem) => {
    try {
      await deleteMutation.mutateAsync(cn.custom_node_id);
      message.success(`已删除 ${cn.node_type}`);
      void customQuery.refetch();
    } catch (e) {
      message.error(`删除失败: ${(e as Error).message}`);
    }
  };

  // ===== 同步系统节点 =====
  const syncMutation = useApiMutation(nodesApi.sync);

  const handleSync = async () => {
    try {
      const result = await syncMutation.mutateAsync();
      message.success(
        `同步完成: 共 ${result.synced}, 新增 ${result.added}, 更新 ${result.updated}, 软删 ${result.removed}`,
      );
      void sysQuery.refetch();
    } catch (e) {
      message.error(`同步失败: ${(e as Error).message}`);
    }
  };

  // ===== 数据合并 =====
  const sysNodes = sysQuery.data ?? [];
  const customNodes = customQuery.data?.items ?? [];

  // 应用过滤
  let filteredSys = sysNodes;
  if (sourceFilter === 'custom') filteredSys = [];
  if (sourceFilter === 'system') filteredSys = sysNodes;
  if (statusFilter === 'disabled') {
    filteredSys = filteredSys.filter((n: NodeDefinition) => !n.enabled);
  } else if (statusFilter === 'enabled') {
    filteredSys = filteredSys.filter((n: NodeDefinition) => n.enabled);
  }
  if (search) {
    const q = search.toLowerCase();
    filteredSys = filteredSys.filter(
      (n) =>
        n.node_type.toLowerCase().includes(q) ||
        n.name.toLowerCase().includes(q) ||
        (n.description ?? '').toLowerCase().includes(q),
    );
  }

  const filteredCustom = customNodes.filter(
    (c: CustomNodeListItem) =>
      !search ||
      c.node_type.toLowerCase().includes(search.toLowerCase()) ||
      c.name.toLowerCase().includes(search.toLowerCase()),
  );

  // ===== 表格列 =====
  const sysColumns: ColumnsType<NodeDefinition> = [
    {
      title: '节点类型',
      dataIndex: 'node_type',
      width: 220,
      render: (v: string, row: NodeDefinition) => (
        <Space>
          <Tag color={row.is_custom ? 'orange' : 'blue'}>
            {row.is_custom ? '自定义' : '系统'}
          </Tag>
          <code style={{ fontSize: 12 }}>{v}</code>
        </Space>
      ),
    },
    {
      title: '名称',
      dataIndex: 'name',
      width: 200,
      render: (v: string, row: NodeDefinition) => (
        <Space>
          <span style={{ fontSize: 16 }}>{row.icon || '📦'}</span>
          {v}
        </Space>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 110,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 80,
      render: (enabled: boolean, row: NodeDefinition) => (
        <Switch
          size="small"
          checked={enabled}
          disabled={!isAdmin}
          loading={toggleMutation.isPending}
          onChange={(v) => handleToggle(row, v)}
        />
      ),
    },
    {
      title: '更新',
      dataIndex: 'updated_at',
      width: 160,
      render: (v: string) => (v ? new Date(v).toLocaleString() : '-'),
    },
    {
      title: '操作',
      width: 220,
      render: (_, row: NodeDefinition) => (
        <Space>
          <Tooltip title="查看 contract">
            <Button
              size="small"
              icon={<InfoCircleOutlined />}
              onClick={() => {
                Modal.info({
                  title: `${row.node_type} contract`,
                  width: 700,
                  content: (
                    <pre style={{ maxHeight: 500, overflow: 'auto', fontSize: 12 }}>
                      {JSON.stringify(row.contract, null, 2)}
                    </pre>
                  ),
                });
              }}
            />
          </Tooltip>
          <Tooltip title="编辑元数据">
            <Button
              size="small"
              icon={<EditOutlined />}
              disabled={!isAdmin}
              onClick={() => openMetaEdit(row)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  const customColumns: ColumnsType<CustomNodeListItem> = [
    {
      title: '节点类型',
      dataIndex: 'node_type',
      width: 220,
      render: (v: string) => (
        <Space>
          <Tag color="orange">自定义</Tag>
          <code style={{ fontSize: 12 }}>{v}</code>
        </Space>
      ),
    },
    {
      title: '名称',
      dataIndex: 'name',
      width: 200,
      render: (v: string, row: CustomNodeListItem) => (
        <Space>
          <span style={{ fontSize: 16 }}>{row.icon || '🛠️'}</span>
          {v}
        </Space>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 110,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: '可见性',
      dataIndex: 'visibility',
      width: 90,
      render: (v: string) => (
        <Tag color={v === 'public' ? 'green' : v === 'tenant' ? 'blue' : 'default'}>{v}</Tag>
      ),
    },
    {
      title: '版本',
      dataIndex: 'current_version_number',
      width: 70,
      render: (v: number | null) => (v ? `v${v}` : '-'),
    },
    {
      title: '试运行',
      dataIndex: 'test_run_count',
      width: 80,
      render: (v: number) => <Tag>{v} 次</Tag>,
    },
    {
      title: '更新',
      dataIndex: 'updated_at',
      width: 160,
      render: (v: string) => (v ? new Date(v).toLocaleString() : '-'),
    },
    {
      title: '操作',
      width: 280,
      render: (_, row: CustomNodeListItem) => (
        <Space>
          <Tooltip title="编辑代码">
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => navigate(`/nodes/${row.custom_node_id}/edit`)}
            />
          </Tooltip>
          <Tooltip title="试运行">
            <Button
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={() => navigate(`/nodes/${row.custom_node_id}/test`)}
            />
          </Tooltip>
          <Popconfirm
            title={`确定删除 ${row.node_type}?`}
            description="软删除后工作流中引用会失败"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={() => handleDelete(row)}
          >
            <Tooltip title="软删除">
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                disabled={!isAdmin}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title={
        <Space>
          <ExperimentOutlined />
          节点管理
          <Tag color="blue">{filteredSys.length} 系统</Tag>
          <Tag color="orange">{filteredCustom.length} 自定义</Tag>
        </Space>
      }
      extra={
        <Space>
          {isAdmin && (
            <Button
              icon={<CloudSyncOutlined />}
              loading={syncMutation.isPending}
              onClick={handleSync}
            >
              同步系统节点
            </Button>
          )}
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => navigate('/nodes/new')}
          >
            新增自定义节点
          </Button>
        </Space>
      }
    >
      {/* 过滤栏 */}
      <Space style={{ marginBottom: 16 }} wrap>
        <Input.Search
          placeholder="搜索节点类型/名称/描述"
          allowClear
          style={{ width: 300 }}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />
        <Select
          value={sourceFilter}
          style={{ width: 130 }}
          onChange={setSourceFilter}
          options={[
            { value: 'all', label: '全部来源' },
            { value: 'system', label: '仅系统' },
            { value: 'custom', label: '仅自定义' },
          ]}
        />
        <Select
          value={statusFilter}
          style={{ width: 130 }}
          onChange={setStatusFilter}
          options={[
            { value: 'all', label: '全部状态' },
            { value: 'enabled', label: '已启用' },
            { value: 'disabled', label: '已停用' },
          ]}
        />
        <span style={{ color: '#999' }}>
          {sysQuery.isLoading || customQuery.isLoading ? '加载中...' : '就绪'}
        </span>
      </Space>

      {/* 系统节点表格 */}
      {sourceFilter !== 'custom' && (
        <>
          <h4 style={{ marginTop: 0 }}>
            <CheckCircleOutlined style={{ color: '#1890ff', marginRight: 6 }} />
            系统节点 ({filteredSys.length})
          </h4>
          <Table<NodeDefinition>
            rowKey="node_type"
            size="small"
            loading={sysQuery.isLoading}
            columns={sysColumns}
            dataSource={filteredSys}
            pagination={false}
          />
        </>
      )}

      {/* 自定义节点表格 */}
      {sourceFilter !== 'system' && (
        <>
          <h4>
            <CodeOutlined style={{ color: '#fa8c16', marginRight: 6 }} />
            自定义节点 ({filteredCustom.length})
          </h4>
          <Table<CustomNodeListItem>
            rowKey="custom_node_id"
            size="small"
            loading={customQuery.isLoading}
            columns={customColumns}
            dataSource={filteredCustom}
            pagination={{
              current: page,
              pageSize,
              total: customQuery.data?.total ?? 0,
              onChange: setPage,
              showSizeChanger: false,
            }}
          />
        </>
      )}

      {/* 元数据编辑 Modal */}
      <Modal
        title={metaEdit ? `编辑 ${metaEdit.node_type}` : ''}
        open={!!metaEdit}
        onCancel={() => setMetaEdit(null)}
        onOk={handleMetaSave}
        confirmLoading={metaSaveMutation.isPending}
      >
        <Form form={metaForm} layout="vertical">
          <Form.Item name="name" label="名称">
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="icon" label="图标 (emoji)">
            <Input maxLength={32} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} maxLength={2000} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

export default NodesListPage;
