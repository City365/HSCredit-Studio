/** 超管后台 — Phase 6 B29. */
import { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Space, App, Button } from 'antd';
import { ReloadOutlined, ClusterOutlined, UserSwitchOutlined } from '@ant-design/icons';
import {
  adminApi,
  type GlobalOverview,
  type TenantListItem,
} from '@/api/admin';

export function AdminPage(): React.ReactElement {
  const { message } = App.useApp();
  const [overview, setOverview] = useState<GlobalOverview | null>(null);
  const [tenants, setTenants] = useState<TenantListItem[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async (): Promise<void> => {
    setLoading(true);
    try {
      const [o, t] = await Promise.all([
        adminApi.overview(),
        adminApi.listTenants(),
      ]);
      setOverview(o);
      setTenants(t.items);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const onUpdateStatus = async (id: string, status: string): Promise<void> => {
    try {
      await adminApi.updateTenantStatus(id, { status, reason: 'E2E test' });
      message.success(`租户状态已更新: ${status}`);
      void load();
    } catch (e) {
      message.error('更新失败: ' + (e as Error).message);
    }
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card title="全平台概览" extra={<Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>}>
        {overview && (
          <Row gutter={16}>
            <Col span={4}><Statistic title="租户总数" value={overview.total_tenants} /></Col>
            <Col span={4}><Statistic title="活跃租户" value={overview.active_tenants} /></Col>
            <Col span={4}><Statistic title="用户总数" value={overview.total_users} /></Col>
            <Col span={4}><Statistic title="工作流" value={overview.total_workflows} /></Col>
            <Col span={4}><Statistic title="Run 总数" value={overview.total_runs} /></Col>
            <Col span={4}><Statistic title="近 24h 审计" value={overview.recent_audit_count} /></Col>
          </Row>
        )}
      </Card>
      <Card title="租户列表">
        <Table<TenantListItem>
          rowKey="tenant_id"
          loading={loading}
          dataSource={tenants}
          pagination={{ pageSize: 20 }}
          columns={[
            { title: 'Slug', dataIndex: 'slug' },
            { title: '名称', dataIndex: 'name' },
            { title: '计划', dataIndex: 'plan', render: (v) => <Tag color="blue">{v}</Tag> },
            {
              title: '状态',
              dataIndex: 'status',
              render: (s: string) => <Tag>{s}</Tag>,
            },
            {
              title: '健康',
              dataIndex: 'health',
              render: (h: string) => (
                <Tag color={h === 'healthy' ? 'success' : h === 'warning' ? 'warning' : 'default'}>
                  {h}
                </Tag>
              ),
            },
            { title: '用户', dataIndex: 'user_count' },
            { title: '工作流', dataIndex: 'workflow_count' },
            {
              title: '操作',
              render: (_, r) => (
                <Space>
                  <Button size="small" icon={<UserSwitchOutlined />} onClick={() => void onUpdateStatus(r.tenant_id, r.status === 'active' ? 'suspended' : 'active')}>
                    {r.status === 'active' ? '停用' : '启用'}
                  </Button>
                  <Button size="small" icon={<ClusterOutlined />}>
                    迁移
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>
    </Space>
  );
}

export default AdminPage;