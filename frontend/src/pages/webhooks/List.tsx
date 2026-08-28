/** Webhooks 列表页 — Phase 8 B35.

支持:
- 列出订阅 + 显示 secret (创建后只显示一次,后续 GET 不显示)
- 创建订阅 (Modal 表单,选择事件)
- 测试投递 (test 按钮)
- 删除订阅
- 跳转详情页
*/
import { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Space,
  Tag,
  Card,
  App,
  Descriptions,
} from 'antd';
import { PlusOutlined, PlayCircleOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { webhooksApi, type WebhookSubscription, type WebhookEvent } from '@/api/webhooks';

export function WebhooksList(): React.ReactElement {
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const [items, setItems] = useState<WebhookSubscription[]>([]);
  const [events, setEvents] = useState<WebhookEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm();
  const [secretModal, setSecretModal] = useState<{ url: string; secret: string } | null>(null);

  const load = async (): Promise<void> => {
    setLoading(true);
    try {
      const [subsR, evR] = await Promise.all([
        webhooksApi.listSubscriptions(),
        webhooksApi.listEvents(),
      ]);
      setItems(subsR.items);
      setEvents(evR.events);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const onCreate = async (values: { url: string; events: string[]; description?: string }): Promise<void> => {
    try {
      const r = await webhooksApi.createSubscription({
        url: values.url,
        events: values.events,
        description: values.description ?? '',
      });
      message.success('订阅创建成功, 请妥善保存 Secret (只显示一次)');
      setSecretModal({ url: r.url, secret: r.secret ?? '' });
      setCreateOpen(false);
      form.resetFields();
      void load();
    } catch (e) {
      message.error('创建失败: ' + (e as Error).message);
    }
  };

  const onTest = async (id: string): Promise<void> => {
    try {
      const r = await webhooksApi.testSubscription(id);
      if (r.success) {
        message.success(`测试投递成功 (HTTP ${r.response_status ?? '?'})`);
      } else {
        message.warning(`测试失败: ${r.error ?? '未知'}`);
      }
    } catch (e) {
      message.error('测试异常: ' + (e as Error).message);
    }
  };

  const onDelete = (id: string, url: string): void => {
    modal.confirm({
      title: '删除订阅?',
      content: `将永久删除订阅: ${url}`,
      okText: '删除',
      okButtonProps: { danger: true },
      onOk: async () => {
        await webhooksApi.deleteSubscription(id);
        message.success('已删除');
        void load();
      },
    });
  };

  return (
    <Card
      title="Webhook 订阅 (Phase 8 B35)"
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建订阅
          </Button>
        </Space>
      }
    >
      <Table<WebhookSubscription>
        rowKey="subscription_id"
        loading={loading}
        dataSource={items}
        pagination={{ pageSize: 20 }}
        columns={[
          { title: 'URL', dataIndex: 'url', ellipsis: true, width: 280 },
          {
            title: '事件',
            dataIndex: 'events',
            render: (evs: string[]) =>
              evs.length === 0 ? (
                <Tag color="blue">全部</Tag>
              ) : (
                <Space size={[0, 4]} wrap>
                  {evs.slice(0, 3).map((e) => <Tag key={e}>{e}</Tag>)}
                  {evs.length > 3 && <Tag>+{evs.length - 3}</Tag>}
                </Space>
              ),
          },
          {
            title: '状态',
            dataIndex: 'active',
            render: (a: boolean) =>
              a ? <Tag color="success">启用</Tag> : <Tag>已停用</Tag>,
          },
          { title: '描述', dataIndex: 'description', ellipsis: true },
          {
            title: '创建时间',
            dataIndex: 'created_at',
            render: (t: string) => new Date(t).toLocaleString('zh-CN'),
          },
          {
            title: '操作',
            render: (_, r) => (
              <Space>
                <Button size="small" onClick={() => navigate(`/webhooks/${r.subscription_id}`)}>
                  详情
                </Button>
                <Button
                  size="small"
                  icon={<PlayCircleOutlined />}
                  onClick={() => void onTest(r.subscription_id)}
                >
                  测试
                </Button>
                <Button
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => onDelete(r.subscription_id, r.url)}
                >
                  删除
                </Button>
              </Space>
            ),
          },
        ]}
      />

      {/* 创建订阅 Modal */}
      <Modal
        title="新建 Webhook 订阅"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        okText="创建"
        cancelText="取消"
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={onCreate}>
          <Form.Item name="url" label="目标 URL" rules={[{ required: true, type: 'url' }]}>
            <Input placeholder="https://your-server.com/webhook" />
          </Form.Item>
          <Form.Item name="events" label="监听事件 (留空 = 全部)">
            <Select
              mode="multiple"
              placeholder="选择事件"
              options={events.map((e) => ({ label: `${e.event} (${e.description})`, value: e.event }))}
              allowClear
            />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input placeholder="订阅用途说明" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Secret 显示 Modal (创建后只显示一次) */}
      <Modal
        title="订阅创建成功 — 请保存 Secret"
        open={!!secretModal}
        onCancel={() => setSecretModal(null)}
        footer={[
          <Button key="ok" type="primary" onClick={() => setSecretModal(null)}>
            我已保存
          </Button>,
        ]}
      >
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="URL">{secretModal?.url}</Descriptions.Item>
          <Descriptions.Item label="Secret (HMAC-SHA256 密钥)">
            <code style={{ wordBreak: 'break-all' }}>{secretModal?.secret}</code>
          </Descriptions.Item>
        </Descriptions>
        <p style={{ color: '#ff4d4f', marginTop: 12 }}>
          ⚠️ Secret 仅显示一次,关闭后无法再次查看。租户端验证 Webhook 签名时需要此密钥。
        </p>
      </Modal>
    </Card>
  );
}

export default WebhooksList;