/** 合同管理 — Phase 4 B21. */
import { useEffect, useState } from 'react';
import { Card, Table, Tag, App, Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { contractsApi, type Contract } from '@/api/contracts';

export function ContractsListPage(): React.ReactElement {
  const { message } = App.useApp();
  const [items, setItems] = useState<Contract[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async (): Promise<void> => {
    setLoading(true);
    try {
      const r = await contractsApi.list();
      setItems(r.items);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  return (
    <Card title="合同管理 (Phase 4 B21)" extra={<Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>}>
      <Table<Contract>
        rowKey="contract_id"
        loading={loading}
        dataSource={items}
        pagination={{ pageSize: 20 }}
        columns={[
          { title: '合同号', dataIndex: 'contract_number' },
          { title: '类型', dataIndex: 'contract_type' },
          {
            title: '状态',
            dataIndex: 'status',
            render: (s: string) => (
              <Tag color={s === 'signed' ? 'success' : s === 'pending' ? 'warning' : 'default'}>
                {s}
              </Tag>
            ),
          },
          {
            title: '生效',
            dataIndex: 'valid_from',
            render: (d: string) => new Date(d).toLocaleDateString('zh-CN'),
          },
          {
            title: '失效',
            dataIndex: 'valid_until',
            render: (d: string) => new Date(d).toLocaleDateString('zh-CN'),
          },
          {
            title: '签署时间',
            dataIndex: 'signed_at',
            render: (d: string | null) => (d ? new Date(d).toLocaleString('zh-CN') : '—'),
          },
        ]}
      />
    </Card>
  );
}

export default ContractsListPage;