/** 账单管理 — Phase 4 B20. */
import { useEffect, useState } from 'react';
import { Card, Table, Tag, Button, Space, App } from 'antd';
import { ReloadOutlined, FileTextOutlined, LinkOutlined } from '@ant-design/icons';
import { billingApi, type Bill } from '@/api/billing';

export function BillingListPage(): React.ReactElement {
  const { message } = App.useApp();
  const [items, setItems] = useState<Bill[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async (): Promise<void> => {
    setLoading(true);
    try {
      const r = await billingApi.list();
      setItems(r.items);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const onIssueInvoice = async (id: string): Promise<void> => {
    try {
      const r = await billingApi.issueInvoice(id);
      message.success(`发票已开: ${r.invoice_number}`);
    } catch (e) {
      message.error('开发票失败: ' + (e as Error).message);
    }
  };

  const onCreatePaymentLink = async (id: string): Promise<void> => {
    try {
      const r = await billingApi.createPaymentLink(id, { channel: 'wechat' });
      window.open(r.payment_url, '_blank');
    } catch (e) {
      message.error('创建支付链接失败: ' + (e as Error).message);
    }
  };

  return (
    <Card title="账单管理 (Phase 4 B20)" extra={<Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>}>
      <Table<Bill>
        rowKey="bill_id"
        loading={loading}
        dataSource={items}
        pagination={{ pageSize: 20 }}
        columns={[
          { title: '账期', dataIndex: 'billing_period' },
          { title: '计划', dataIndex: 'plan' },
          {
            title: '状态',
            dataIndex: 'status',
            render: (s: string) => (
              <Tag color={s === 'paid' ? 'success' : s === 'pending' ? 'warning' : 'default'}>
                {s}
              </Tag>
            ),
          },
          {
            title: '总额',
            dataIndex: 'total_amount',
            render: (v: number, r) => `¥ ${v.toFixed(2)} ${r.currency}`,
          },
          {
            title: '到期日',
            dataIndex: 'due_date',
            render: (d: string) => new Date(d).toLocaleDateString('zh-CN'),
          },
          {
            title: '支付时间',
            dataIndex: 'paid_at',
            render: (d: string | null) => (d ? new Date(d).toLocaleString('zh-CN') : '—'),
          },
          {
            title: '操作',
            render: (_, r) => (
              <Space>
                <Button size="small" icon={<FileTextOutlined />} onClick={() => void onIssueInvoice(r.bill_id)}>
                  开发票
                </Button>
                <Button size="small" icon={<LinkOutlined />} onClick={() => void onCreatePaymentLink(r.bill_id)}>
                  支付链接
                </Button>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}

export default BillingListPage;