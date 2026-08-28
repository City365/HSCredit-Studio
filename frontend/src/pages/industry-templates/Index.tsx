/** 行业模板市场 — Phase 6 B30. */
import { useEffect, useState } from 'react';
import { Card, Table, Tag, Button, Modal, Descriptions, App, Space } from 'antd';
import { ReloadOutlined, EyeOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { industryTemplatesApi, type IndustryTemplate, type IndustryTemplateDetail } from '@/api/industry-templates';

export function IndustryTemplatesPage(): React.ReactElement {
  const { message } = App.useApp();
  const [items, setItems] = useState<IndustryTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<IndustryTemplateDetail | null>(null);

  const load = async (): Promise<void> => {
    setLoading(true);
    try {
      const r = await industryTemplatesApi.list();
      setItems(r.items);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const onView = async (id: string): Promise<void> => {
    try {
      const d = await industryTemplatesApi.get(id);
      setDetail(d);
    } catch (e) {
      message.error('加载详情失败: ' + (e as Error).message);
    }
  };

  const onInstantiate = async (id: string): Promise<void> => {
    try {
      const r = await industryTemplatesApi.instantiate({ template_id: id });
      message.success(`已实例化工作流: ${r.workflow_name} (${r.nodes_count} 节点)`);
    } catch (e) {
      message.error('实例化失败: ' + (e as Error).message);
    }
  };

  return (
    <Card title="行业模板市场 (Phase 6 B30)" extra={<Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>}>
      <Table<IndustryTemplate>
        rowKey="template_id"
        loading={loading}
        dataSource={items}
        pagination={false}
        columns={[
          { title: '行业', dataIndex: 'industry', render: (v) => <Tag color="blue">{v}</Tag> },
          { title: '名称', dataIndex: 'name' },
          { title: '说明', dataIndex: 'description', ellipsis: true },
          { title: '节点数', dataIndex: 'node_count' },
          { title: '目标列', dataIndex: 'target_column' },
          { title: '模型类型', dataIndex: 'model_type' },
          {
            title: '操作',
            render: (_, r) => (
              <Space>
                <Button size="small" icon={<EyeOutlined />} onClick={() => void onView(r.template_id)}>
                  预览
                </Button>
                <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => void onInstantiate(r.template_id)}>
                  实例化
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal title="模板详情" open={!!detail} onCancel={() => setDetail(null)} footer={null} width={700}>
        {detail && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="名称">{detail.name}</Descriptions.Item>
            <Descriptions.Item label="行业">{detail.industry}</Descriptions.Item>
            <Descriptions.Item label="目标列">{detail.target_column}</Descriptions.Item>
            <Descriptions.Item label="节点数">{detail.nodes.length}</Descriptions.Item>
            <Descriptions.Item label="边数">{detail.edges.length}</Descriptions.Item>
            <Descriptions.Item label="默认数据集">{detail.default_dataset}</Descriptions.Item>
            <Descriptions.Item label="评分公式"><code>{detail.score_formula}</code></Descriptions.Item>
            <Descriptions.Item label="说明">{detail.description}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </Card>
  );
}

export default IndustryTemplatesPage;