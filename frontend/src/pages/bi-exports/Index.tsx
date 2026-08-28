/** BI 报表导出页 — Phase 7 B33.

支持:
- 数据集列表 (audit_events / runs / billing / usage_daily / ...)
- 选择格式 (CSV / NDJSON / Parquet) 触发下载
- BI 数据库视图列表
- PowerBI / Tableau / FineBI 连接器模板展示
- 连接器连通性测试
*/
import { useEffect, useState } from 'react';
import {
  Card,
  Tabs,
  Table,
  Button,
  Space,
  Tag,
  Select,
  App,
  Descriptions,
  Empty,
} from 'antd';
import {
  DownloadOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '@/stores/authStore';
import { biExportsApi, type BIDataset, type BIView } from '@/api/bi-exports';

export function BIExportsPage(): React.ReactElement {
  const { message } = App.useApp();
  const tenant = useAuthStore((s) => s.tenantSlug);
  const user = useAuthStore((s) => s.user);
  const [datasets, setDatasets] = useState<BIDataset[]>([]);
  const [views, setViews] = useState<BIView[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedDataset, setSelectedDataset] = useState<string>('audit_events');
  const [exportFormat, setExportFormat] = useState<'csv' | 'ndjson' | 'parquet'>('csv');
  const [connectorResult, setConnectorResult] = useState<{ name: string; healthy: boolean; message: string } | null>(null);
  const [tplPreview, setTplPreview] = useState<{ title: string; content: string } | null>(null);

  const load = async (): Promise<void> => {
    setLoading(true);
    try {
      const [d, v] = await Promise.all([
        biExportsApi.listDatasets(),
        biExportsApi.listViews(),
      ]);
      setDatasets(d.items);
      setViews(v.items);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const onExport = async (): Promise<void> => {
    try {
      await biExportsApi.downloadExport(selectedDataset, exportFormat);
      message.success(`已下载 ${selectedDataset}.${exportFormat}`);
    } catch (e) {
      message.error('导出失败: ' + (e as Error).message);
    }
  };

  const onTestConnector = async (
    name: 'powerbi' | 'tableau' | 'finebi',
  ): Promise<void> => {
    try {
      const r = await biExportsApi.testConnector(name);
      setConnectorResult({ name, healthy: r.healthy, message: r.message });
    } catch (e) {
      message.error('测试失败: ' + (e as Error).message);
    }
  };

  const onShowTemplate = async (
    name: 'powerbi' | 'tableau' | 'finebi',
  ): Promise<void> => {
    if (!tenant) {
      message.warning('未选择租户');
      return;
    }
    // 用 user.user_id 作为 tenant_uuid 占位 (后端模板仅用作内容生成)
    const params = {
      tenant_slug: tenant,
      tenant_uuid: user?.user_id ?? '00000000-0000-0000-0000-000000000000',
    };
    try {
      if (name === 'powerbi') {
        const r = await biExportsApi.getPowerBITemplate({
          ...params,
          base_url: window.location.origin.replace(/\/$/, '').replace(':3000', ':8003'),
        });
        setTplPreview({
          title: 'PowerBI 直连模板 (M Query)',
          content: r.queries.map((q) => `# ${q.display_name}\n${q.m_query}`).join('\n\n'),
        });
      } else if (name === 'tableau') {
        const r = await biExportsApi.getTableauTemplate(params);
        setTplPreview({ title: 'Tableau .tds XML', content: r.schema_xml });
      } else {
        const r = await biExportsApi.getFineBITemplate(params);
        setTplPreview({
          title: 'FineBI 配置 XML',
          content: r.config_xml,
        });
      }
    } catch (e) {
      message.error('加载模板失败: ' + (e as Error).message);
    }
  };

  return (
    <Tabs
      defaultActiveKey="datasets"
      items={[
        {
          key: 'datasets',
          label: '数据集导出',
          children: (
            <Card>
              <Space.Compact style={{ marginBottom: 16 }}>
                <Select
                  value={selectedDataset}
                  onChange={setSelectedDataset}
                  style={{ width: 220 }}
                  options={datasets.map((d) => ({ label: d.name, value: d.key }))}
                />
                <Select
                  value={exportFormat}
                  onChange={(v) => setExportFormat(v)}
                  style={{ width: 140 }}
                  options={[
                    { label: 'CSV (UTF-8 BOM)', value: 'csv' },
                    { label: 'NDJSON', value: 'ndjson' },
                    { label: 'Parquet', value: 'parquet' },
                  ]}
                />
                <Button
                  type="primary"
                  icon={<DownloadOutlined />}
                  onClick={() => void onExport()}
                >
                  下载
                </Button>
              </Space.Compact>

              <Table<BIDataset>
                rowKey="key"
                loading={loading}
                dataSource={datasets}
                pagination={false}
                columns={[
                  { title: 'Key', dataIndex: 'key' },
                  { title: '名称', dataIndex: 'name' },
                  { title: '说明', dataIndex: 'description', ellipsis: true },
                  {
                    title: '字段数',
                    dataIndex: 'fields',
                    render: (f: string[]) => f.length,
                  },
                  {
                    title: '能力',
                    render: (_, r) => (
                      <Space>
                        {r.supports_streaming && <Tag color="green">流式</Tag>}
                        {r.supports_parquet && <Tag color="blue">Parquet</Tag>}
                      </Space>
                    ),
                  },
                ]}
              />
            </Card>
          ),
        },
        {
          key: 'views',
          label: 'BI 数据库视图',
          children: (
            <Card>
              <Table<BIView>
                rowKey="name"
                loading={loading}
                dataSource={views}
                pagination={false}
                columns={[
                  { title: '视图名', dataIndex: 'name' },
                  { title: 'Schema', dataIndex: 'schema' },
                  { title: '说明', dataIndex: 'description' },
                  {
                    title: '列数',
                    dataIndex: 'columns',
                    render: (c: string[]) => c.length,
                  },
                  {
                    title: '预览列',
                    dataIndex: 'columns',
                    render: (c: string[]) => c.slice(0, 5).join(', ') + (c.length > 5 ? '...' : ''),
                  },
                ]}
              />
              {views.length === 0 && (
                <Empty description="尚未运行 alembic 0012_bi_views 迁移" />
              )}
            </Card>
          ),
        },
        {
          key: 'connectors',
          label: 'BI 工具连接器',
          children: (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <Card title="PowerBI / Tableau / 帆软 FineBI" extra={<DatabaseOutlined />}>
                <Space wrap>
                  <Button icon={<DownloadOutlined />} onClick={() => void onShowTemplate('powerbi')}>
                    查看 PowerBI 模板
                  </Button>
                  <Button icon={<DownloadOutlined />} onClick={() => void onShowTemplate('tableau')}>
                    查看 Tableau 模板
                  </Button>
                  <Button icon={<DownloadOutlined />} onClick={() => void onShowTemplate('finebi')}>
                    查看 FineBI 模板
                  </Button>
                  <Button icon={<CheckCircleOutlined />} onClick={() => void onTestConnector('powerbi')}>
                    测试 PowerBI 连接
                  </Button>
                  <Button icon={<CheckCircleOutlined />} onClick={() => void onTestConnector('tableau')}>
                    测试 Tableau 连接
                  </Button>
                  <Button icon={<CheckCircleOutlined />} onClick={() => void onTestConnector('finebi')}>
                    测试 FineBI 连接
                  </Button>
                </Space>
              </Card>
              {connectorResult && (
                <Card title={`${connectorResult.name} 连接测试结果`}>
                  <Descriptions column={1} bordered>
                    <Descriptions.Item label="连接器">{connectorResult.name}</Descriptions.Item>
                    <Descriptions.Item label="健康状态">
                      {connectorResult.healthy ? (
                        <Tag color="success">✓ Healthy</Tag>
                      ) : (
                        <Tag color="error">✗ Unhealthy</Tag>
                      )}
                    </Descriptions.Item>
                    <Descriptions.Item label="说明">{connectorResult.message}</Descriptions.Item>
                  </Descriptions>
                </Card>
              )}
              {tplPreview && (
                <Card title={tplPreview.title}>
                  <pre style={{ background: '#f5f5f5', padding: 12, overflow: 'auto', maxHeight: 400 }}>
                    {tplPreview.content}
                  </pre>
                </Card>
              )}
            </Space>
          ),
        },
      ]}
    />
  );
}

export default BIExportsPage;