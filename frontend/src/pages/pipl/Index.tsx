/** PIPL 数据保护 — Phase 5 B26. */
import { useEffect, useState } from 'react';
import { Card, Tabs, Table, Tag, Button, Form, Select, Input, Space, App, Descriptions } from 'antd';
import {  CheckCircleOutlined, DeleteOutlined, DownloadOutlined } from '@ant-design/icons';
import { piplApi, type ConsentRecord, type DsrItem, type CrossBorderTransfer } from '@/api/pipl';

export function PiplPage(): React.ReactElement {
  const { message, modal } = App.useApp();
  const [consents, setConsents] = useState<ConsentRecord[]>([]);
  const [dsrs, setDsrs] = useState<DsrItem[]>([]);
  const [transfers, setTransfers] = useState<CrossBorderTransfer[]>([]);
  const [policy, setPolicy] = useState<{ version: string; content_md: string } | null>(null);

  const load = async (): Promise<void> => {
    try {
      const [c, d, t, p] = await Promise.all([
        piplApi.listMyConsents(),
        piplApi.listMyDsrs(),
        piplApi.listCrossBorder(),
        piplApi.getCurrentPolicy(),
      ]);
      setConsents(c.items);
      setDsrs(d.items);
      setTransfers(t.items);
      setPolicy(p);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    }
  };

  useEffect(() => { void load(); }, []);

  const onGrant = async (values: { purpose: string }): Promise<void> => {
    try {
      await piplApi.grantConsent({ purpose: values.purpose });
      message.success('已授予同意');
      void load();
    } catch (e) {
      message.error('授予失败: ' + (e as Error).message);
    }
  };

  const onRevoke = async (purpose: string): Promise<void> => {
    try {
      await piplApi.revokeConsent({ purpose });
      message.success('已撤回同意');
      void load();
    } catch (e) {
      message.error('撤回失败: ' + (e as Error).message);
    }
  };

  const onSubmitDsr = async (values: {
    request_type: 'query' | 'delete' | 'correct' | 'portability';
    reason: string;
  }): Promise<void> => {
    try {
      await piplApi.submitDsr(values);
      message.success('DSR 已提交 (PIPL 30 天内响应)');
      void load();
    } catch (e) {
      message.error('提交失败: ' + (e as Error).message);
    }
  };

  const onDelete = async (): Promise<void> => {
    modal.confirm({
      title: '请求删除我的所有数据?',
      content: '这将触发数据清除流程 (PIPL 第 47 条匿名化)',
      okText: '确认删除',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const r = await piplApi.anonymizeMyData();
          message.warning(`已匿名化 ${r.affected_fields.length} 个字段`);
        } catch (e) {
          message.error('删除失败: ' + (e as Error).message);
        }
      },
    });
  };

  return (
    <Tabs
      defaultActiveKey="consents"
      items={[
        {
          key: 'consents',
          label: '我的同意记录',
          children: (
            <Card>
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Form layout="inline" onFinish={onGrant}>
                  <Form.Item name="purpose" rules={[{ required: true }]}>
                    <Select
                      placeholder="选择目的"
                      style={{ width: 220 }}
                      options={[
                        { label: '服务必需 (essential)', value: 'essential' },
                        { label: '营销 (marketing)', value: 'marketing' },
                        { label: '分析 (analytics)', value: 'analytics' },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" icon={<CheckCircleOutlined />} htmlType="submit">
                      授予同意
                    </Button>
                  </Form.Item>
                </Form>
                <Table<ConsentRecord>
                  rowKey="consent_id"
                  dataSource={consents}
                  pagination={false}
                  columns={[
                    { title: '目的', dataIndex: 'purpose' },
                    {
                      title: '状态',
                      dataIndex: 'granted',
                      render: (g: boolean, r) => (
                        <Space>
                          <Tag color={g ? 'success' : 'default'}>{g ? '已同意' : '已撤回'}</Tag>
                          {g && (
                            <Button size="small" danger onClick={() => void onRevoke(r.purpose)}>
                              撤回
                            </Button>
                          )}
                        </Space>
                      ),
                    },
                    {
                      title: '同意时间',
                      dataIndex: 'granted_at',
                      render: (t: string) => new Date(t).toLocaleString('zh-CN'),
                    },
                    {
                      title: '撤回时间',
                      dataIndex: 'revoked_at',
                      render: (t: string | null) => (t ? new Date(t).toLocaleString('zh-CN') : '—'),
                    },
                  ]}
                />
              </Space>
            </Card>
          ),
        },
        {
          key: 'dsr',
          label: '数据主体请求 (DSR)',
          children: (
            <Card>
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Form layout="vertical" onFinish={onSubmitDsr} style={{ maxWidth: 600 }}>
                  <Form.Item name="request_type" label="请求类型" rules={[{ required: true }]}>
                    <Select
                      options={[
                        { label: '查询我的数据', value: 'query' },
                        { label: '更正我的数据', value: 'correct' },
                        { label: '数据可携', value: 'portability' },
                        { label: '删除我的数据', value: 'delete' },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item name="reason" label="原因" rules={[{ required: true }]}>
                    <Input.TextArea rows={2} />
                  </Form.Item>
                  <Space>
                    <Form.Item>
                      <Button type="primary" htmlType="submit">
                        提交 DSR
                      </Button>
                    </Form.Item>
                    <Form.Item>
                      <Button danger icon={<DeleteOutlined />} onClick={onDelete}>
                        一键匿名化
                      </Button>
                    </Form.Item>
                  </Space>
                </Form>
                <Table<DsrItem>
                  rowKey="request_id"
                  dataSource={dsrs}
                  pagination={false}
                  columns={[
                    { title: '类型', dataIndex: 'request_type', render: (v: string) => <Tag>{v}</Tag> },
                    {
                      title: '状态',
                      dataIndex: 'status',
                      render: (s: string) => <Tag>{s}</Tag>,
                    },
                    { title: '原因', dataIndex: 'reason', ellipsis: true },
                    {
                      title: '提交时间',
                      dataIndex: 'submitted_at',
                      render: (t: string) => new Date(t).toLocaleString('zh-CN'),
                    },
                    {
                      title: '截止时间 (30 天)',
                      dataIndex: 'due_at',
                      render: (t: string) => new Date(t).toLocaleDateString('zh-CN'),
                    },
                  ]}
                />
              </Space>
            </Card>
          ),
        },
        {
          key: 'cross-border',
          label: '跨境传输',
          children: (
            <Card>
              <Table<CrossBorderTransfer>
                rowKey="transfer_id"
                dataSource={transfers}
                pagination={false}
                columns={[
                  { title: '目标国家', dataIndex: 'destination_country' },
                  { title: '接收方', dataIndex: 'recipient' },
                  { title: '法律基础', dataIndex: 'legal_basis' },
                  {
                    title: '审批',
                    dataIndex: 'approved',
                    render: (a: boolean) => <Tag color={a ? 'success' : 'warning'}>{a ? '已批准' : '待审'}</Tag>,
                  },
                ]}
              />
            </Card>
          ),
        },
        {
          key: 'policy',
          label: '隐私政策',
          children: (
            <Card>
              {policy ? (
                <Descriptions column={1} bordered>
                  <Descriptions.Item label="版本">{policy.version}</Descriptions.Item>
                  <Descriptions.Item label="内容 (摘要)">{policy.content_md}</Descriptions.Item>
                </Descriptions>
              ) : (
                <Button icon={<DownloadOutlined />} onClick={() => void load()}>加载</Button>
              )}
            </Card>
          ),
        },
      ]}
    />
  );
}

export default PiplPage;