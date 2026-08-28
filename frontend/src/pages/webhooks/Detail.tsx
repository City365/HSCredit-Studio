/** Webhook 详情页 — Phase 8 B35.

显示:
- 订阅详情 (URL, events, active, description)
- 投递日志列表 (status, response_status, last_error, scheduled_at, delivered_at)
- 操作: 测试投递, 手动重试失败投递, 跳回列表
*/
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Descriptions, Table, Tag, Button, Space, App } from 'antd';
import {
  ArrowLeftOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import {
  webhooksApi,
  type WebhookSubscription,
  type WebhookDelivery,
} from '@/api/webhooks';

const statusColors: Record<string, string> = {
  success: 'success',
  failed: 'error',
  retrying: 'warning',
  pending: 'processing',
  cancelled: 'default',
};

export function WebhookDetail(): React.ReactElement {
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [sub, setSub] = useState<WebhookSubscription | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async (): Promise<void> => {
    if (!id) return;
    setLoading(true);
    try {
      const [s, d] = await Promise.all([
        webhooksApi.getSubscription(id),
        webhooksApi.listDeliveries(id),
      ]);
      setSub(s);
      setDeliveries(d.items);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [id]);

  const onTest = async (): Promise<void> => {
    if (!id) return;
    const r = await webhooksApi.testSubscription(id);
    message[r.success ? 'success' : 'warning'](
      r.success
        ? `测试成功 (HTTP ${r.response_status})`
        : `测试失败: ${r.error ?? '未知'}`,
    );
    void load();
  };

  const onRetry = async (deliveryId: string): Promise<void> => {
    try {
      await webhooksApi.retryDelivery(deliveryId);
      message.success('已触发重试');
      void load();
    } catch (e) {
      message.error('重试失败: ' + (e as Error).message);
    }
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/webhooks')}>
            返回
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>
            刷新
          </Button>
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => void onTest()}>
            测试投递
          </Button>
        </Space>
      </Card>

      <Card title="订阅详情">
        {sub && (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="订阅 ID" span={2}>
              <code>{sub.subscription_id}</code>
            </Descriptions.Item>
            <Descriptions.Item label="URL" span={2}>
              <code>{sub.url}</code>
            </Descriptions.Item>
            <Descriptions.Item label="租户 ID" span={2}>
              <code>{sub.tenant_id}</code>
            </Descriptions.Item>
            <Descriptions.Item label="监听事件" span={2}>
              {sub.events.length === 0 ? (
                <Tag color="blue">全部事件</Tag>
              ) : (
                <Space size={[4, 4]} wrap>
                  {sub.events.map((e) => <Tag key={e}>{e}</Tag>)}
                </Space>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              {sub.active ? <Tag color="success">启用</Tag> : <Tag>已停用</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="描述">{sub.description || '—'}</Descriptions.Item>
            <Descriptions.Item label="创建时间" span={2}>
              {new Date(sub.created_at).toLocaleString('zh-CN')}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Card>

      <Card title={`投递日志 (${deliveries.length})`}>
        <Table<WebhookDelivery>
          rowKey="delivery_id"
          loading={loading}
          dataSource={deliveries}
          pagination={{ pageSize: 20 }}
          columns={[
            { title: '事件', dataIndex: 'event' },
            {
              title: '状态',
              dataIndex: 'status',
              render: (s: string) => <Tag color={statusColors[s] ?? 'default'}>{s}</Tag>,
            },
            { title: '尝试', dataIndex: 'attempt', width: 60 },
            {
              title: 'HTTP',
              dataIndex: 'response_status',
              render: (s: number | null) => s ?? '—',
            },
            {
              title: '错误',
              dataIndex: 'last_error',
              ellipsis: true,
              render: (e: string | null) => e ?? '—',
            },
            {
              title: '计划时间',
              dataIndex: 'scheduled_at',
              render: (t: string) => new Date(t).toLocaleString('zh-CN'),
            },
            {
              title: '送达时间',
              dataIndex: 'delivered_at',
              render: (t: string | null) => (t ? new Date(t).toLocaleString('zh-CN') : '—'),
            },
            {
              title: '操作',
              render: (_, r) =>
                r.status === 'failed' || r.status === 'retrying' ? (
                  <Button size="small" onClick={() => void onRetry(r.delivery_id)}>
                    重试
                  </Button>
                ) : null,
            },
          ]}
        />
      </Card>
    </Space>
  );
}

export default WebhookDetail;