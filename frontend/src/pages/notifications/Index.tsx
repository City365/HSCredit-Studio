/** 通知配置 — Phase 5 B23. */
import { useEffect, useState } from 'react';
import { Card, Tabs, Table, Tag, Button, Form, Input, Select, App } from 'antd';
import {  SendOutlined } from '@ant-design/icons';
import {
  notificationsApi,
  type NotificationConfig,
  type NotificationTemplate,
  type NotificationLog,
} from '@/api/notifications';

export function NotificationsPage(): React.ReactElement {
  const { message } = App.useApp();
  const [templates, setTemplates] = useState<NotificationTemplate[]>([]);
  const [configs, setConfigs] = useState<NotificationConfig[]>([]);
  const [logs, setLogs] = useState<NotificationLog[]>([]);

  const load = async (): Promise<void> => {
    try {
      const [t, c, l] = await Promise.all([
        notificationsApi.listTemplates(),
        notificationsApi.listConfigs(),
        notificationsApi.listLogs(),
      ]);
      setTemplates(t.items);
      setConfigs(c.items);
      setLogs(l.items);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    }
  };

  useEffect(() => { void load(); }, []);

  const onTest = async (values: { template_key: string; recipient: string }): Promise<void> => {
    try {
      const r = await notificationsApi.sendTest({
        template_key: values.template_key,
        recipient: values.recipient,
        dry_run: false,
      });
      message.success(`已发送: ${r.results.length} 个通道, 成功 ${r.results.filter((x) => x.success).length}`);
    } catch (e) {
      message.error('发送失败: ' + (e as Error).message);
    }
  };

  return (
    <Tabs
      defaultActiveKey="configs"
      items={[
        {
          key: 'configs',
          label: '通知配置',
          children: (
            <Card>
              <Table<NotificationConfig>
                rowKey="config_id"
                dataSource={configs}
                pagination={false}
                columns={[
                  { title: '通道', dataIndex: 'channel', render: (v) => <Tag>{v}</Tag> },
                  { title: '接收方', dataIndex: 'recipient' },
                  { title: '事件', dataIndex: 'events', render: (e: string[]) => e.join(', ') || '全部' },
                  {
                    title: '启用',
                    dataIndex: 'active',
                    render: (a: boolean) => a ? <Tag color="success">是</Tag> : <Tag>否</Tag>,
                  },
                ]}
              />
            </Card>
          ),
        },
        {
          key: 'templates',
          label: '通知模板',
          children: (
            <Card>
              <Table<NotificationTemplate>
                rowKey="key"
                dataSource={templates}
                pagination={false}
                columns={[
                  { title: 'Key', dataIndex: 'key' },
                  { title: '标题', dataIndex: 'title_template', ellipsis: true },
                  { title: '正文', dataIndex: 'body_template', ellipsis: true },
                  { title: '默认通道', dataIndex: 'default_channels', render: (c: string[]) => c.join(', ') },
                ]}
              />
            </Card>
          ),
        },
        {
          key: 'logs',
          label: '发送历史',
          children: (
            <Card>
              <Table<NotificationLog>
                rowKey="log_id"
                dataSource={logs}
                pagination={{ pageSize: 20 }}
                columns={[
                  { title: '模板', dataIndex: 'template_key' },
                  { title: '通道', dataIndex: 'channel' },
                  { title: '接收方', dataIndex: 'recipient' },
                  {
                    title: '状态',
                    dataIndex: 'status',
                    render: (s: string) => <Tag color={s === 'success' ? 'success' : 'error'}>{s}</Tag>,
                  },
                  {
                    title: '发送时间',
                    dataIndex: 'sent_at',
                    render: (t: string) => new Date(t).toLocaleString('zh-CN'),
                  },
                  { title: '错误', dataIndex: 'error', ellipsis: true },
                ]}
              />
            </Card>
          ),
        },
        {
          key: 'test',
          label: '测试发送',
          children: (
            <Card>
              <Form layout="vertical" onFinish={onTest} style={{ maxWidth: 600 }}>
                <Form.Item name="template_key" label="模板" rules={[{ required: true }]}>
                  <Select
                    options={templates.map((t) => ({ label: t.key, value: t.key }))}
                  />
                </Form.Item>
                <Form.Item name="recipient" label="接收方" rules={[{ required: true }]}>
                  <Input placeholder="邮箱 / webhook URL" />
                </Form.Item>
                <Form.Item>
                  <Button type="primary" icon={<SendOutlined />} htmlType="submit">
                    发送测试
                  </Button>
                </Form.Item>
              </Form>
            </Card>
          ),
        },
      ]}
    />
  );
}

export default NotificationsPage;