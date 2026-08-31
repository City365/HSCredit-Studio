/** RBAC 权限矩阵 — Phase 6 B28. */
import { useEffect, useState } from 'react';
import { Card, Tabs, Table, Tag, Space, App, Button, Form, Select } from 'antd';
import { SafetyOutlined, AuditOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  rbacApi,
  type PermissionMatrix,
  type RolePolicy,
  type RoleAuditItem,
} from '@/api/rbac';

export function RbacPage(): React.ReactElement {
  const { message } = App.useApp();
  const [matrix, setMatrix] = useState<PermissionMatrix | null>(null);
  const [policies, setPolicies] = useState<RolePolicy[]>([]);
  const [audit, setAudit] = useState<RoleAuditItem[]>([]);
  const [checkResult, setCheckResult] = useState<{ allowed: boolean; reason?: string } | null>(null);

  const load = async (): Promise<void> => {
    try {
      const [m, p, a] = await Promise.all([
        rbacApi.getMatrix(),
        rbacApi.listPolicies(),
        rbacApi.listAudit(),
      ]);
      setMatrix(m);
      setPolicies(p.items);
      setAudit(a.items);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    }
  };

  useEffect(() => { void load(); }, []);

  const onCheck = async (values: { resource: string; action: string }): Promise<void> => {
    try {
      const r = await rbacApi.check(values);
      setCheckResult(r);
      message[r.allowed ? 'success' : 'warning'](r.allowed ? '✓ 允许' : `✗ 拒绝: ${r.reason ?? '权限不足'}`);
    } catch (e) {
      message.error('检查失败: ' + (e as Error).message);
    }
  };

  return (
    <Tabs
      defaultActiveKey="matrix"
      items={[
        {
          key: 'matrix',
          label: <><SafetyOutlined /> 权限矩阵</>,
          children: (
            <Card extra={<Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>}>
              {matrix && (
                <div>
                  {/* 角色说明卡 */}
                  <Card type="inner" title="角色等级 (rank 越高权限越大)" style={{ marginBottom: 16 }}>
                    <Space size="middle" wrap>
                      {matrix.roles.map((r) => (
                        <Card key={r.role} size="small" style={{ width: 220 }}>
                          <Space direction="vertical" size={2}>
                            <Space>
                              <Tag color="blue">{r.role}</Tag>
                              <span style={{ fontWeight: 600 }}>{r.label}</span>
                            </Space>
                            <span style={{ color: '#666', fontSize: 12 }}>
                              rank={r.rank}{r.is_tenant_scoped ? ' · 租户内' : ' · 全平台'}
                            </span>
                            <span style={{ fontSize: 12 }}>{r.description}</span>
                          </Space>
                        </Card>
                      ))}
                    </Space>
                  </Card>

                  {/* 权限矩阵 */}
                  <Card type="inner" title="权限矩阵 (resource × role)">
                    <Table
                      rowKey="resource"
                      pagination={false}
                      scroll={{ x: 'max-content' }}
                      dataSource={matrix.resources.map((res) => {
                        const row: Record<string, unknown> = { key: res, resource: res };
                        matrix.roles.forEach((r) => {
                          row[r.role] = matrix.matrix[r.role]?.[res] ?? null;
                        });
                        return row;
                      })}
                      columns={[
                        {
                          title: '资源',
                          dataIndex: 'resource',
                          fixed: 'left' as const,
                          width: 110,
                          render: (v: string) => <Tag color="purple">{v}</Tag>,
                        },
                        ...matrix.roles.map((r) => ({
                          title: r.label,
                          dataIndex: r.role,
                          render: (v: string | null) => (
                            <Tag color={v === 'admin' ? 'red' : v === 'write' ? 'orange' : v === 'read' ? 'blue' : 'default'}>
                              {v ?? '—'}
                            </Tag>
                          ),
                        })),
                      ]}
                    />
                  </Card>

                  {/* 操作权限图例 */}
                  <Card type="inner" title="操作权限图例" style={{ marginTop: 16 }}>
                    <Space wrap>
                      <Tag color="red">admin (管理)</Tag>
                      <Tag color="orange">write (读写)</Tag>
                      <Tag color="blue">read (只读)</Tag>
                      <Tag>— (无权限)</Tag>
                    </Space>
                  </Card>
                </div>
              )}
            </Card>
          ),
        },
        {
          key: 'check',
          label: '权限校验',
          children: (
            <Card>
              <Form layout="vertical" onFinish={onCheck} style={{ maxWidth: 500 }}>
                <Form.Item name="resource" label="资源" rules={[{ required: true }]}>
                  <Select
                    options={[
                      { label: 'workflow', value: 'workflow' },
                      { label: 'run', value: 'run' },
                      { label: 'model', value: 'model' },
                      { label: 'template', value: 'template' },
                      { label: 'billing', value: 'billing' },
                    ]}
                  />
                </Form.Item>
                <Form.Item name="action" label="动作" rules={[{ required: true }]}>
                  <Select
                    options={[
                      { label: 'read', value: 'read' },
                      { label: 'write', value: 'write' },
                      { label: 'admin', value: 'admin' },
                    ]}
                  />
                </Form.Item>
                <Form.Item>
                  <Button type="primary" htmlType="submit">
                    检查
                  </Button>
                </Form.Item>
              </Form>
              {checkResult && (
                <Space style={{ marginTop: 16 }}>
                  <Tag color={checkResult.allowed ? 'success' : 'error'}>
                    {checkResult.allowed ? '✓ ALLOWED' : '✗ DENIED'}
                  </Tag>
                  {checkResult.reason && <span>{checkResult.reason}</span>}
                </Space>
              )}
            </Card>
          ),
        },
        {
          key: 'policies',
          label: '角色策略',
          children: (
            <Card>
              <Table<RolePolicy>
                rowKey="policy_id"
                dataSource={policies}
                pagination={{ pageSize: 20 }}
                columns={[
                  { title: '角色', dataIndex: 'role' },
                  { title: '资源', dataIndex: 'resource' },
                  { title: '动作', dataIndex: 'action' },
                  {
                    title: '范围',
                    dataIndex: 'tenant_id',
                    render: (v: string | null) => (v ? <Tag color="purple">租户 {v.slice(0, 8)}</Tag> : <Tag color="blue">全局</Tag>),
                  },
                ]}
              />
            </Card>
          ),
        },
        {
          key: 'audit',
          label: <><AuditOutlined /> 角色变更审计</>,
          children: (
            <Card>
              <Table<RoleAuditItem>
                rowKey="audit_id"
                dataSource={audit}
                pagination={{ pageSize: 20 }}
                columns={[
                  { title: '用户', dataIndex: 'user_id', ellipsis: true },
                  {
                    title: '变更',
                    render: (_, r) => (
                      <Space>
                        {r.old_role && <Tag>{r.old_role}</Tag>}
                        <span>→</span>
                        <Tag color="blue">{r.new_role}</Tag>
                      </Space>
                    ),
                  },
                  { title: '操作人', dataIndex: 'changed_by', ellipsis: true },
                  { title: '原因', dataIndex: 'reason', ellipsis: true },
                  {
                    title: '时间',
                    dataIndex: 'created_at',
                    render: (t: string) => new Date(t).toLocaleString('zh-CN'),
                  },
                ]}
              />
            </Card>
          ),
        },
      ]}
    />
  );
}

export default RbacPage;