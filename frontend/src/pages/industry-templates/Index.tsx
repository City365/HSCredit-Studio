/** 行业模板市场 — Phase 6 B30. */
import { useEffect, useState } from 'react';
import { Card, Table, Tag, Button, Modal, Descriptions, App, Space, Typography } from 'antd';
import { ReloadOutlined, EyeOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { industryTemplatesApi, type IndustryTemplate, type IndustryTemplateDetail } from '@/api/industry-templates';

interface InstantiateResult {
  template_id: string;
  template_name: string;
  workflow_id: string;
  workflow_name: string;
  node_count: number;
  edge_count: number;
  created_at: string;
}

export function IndustryTemplatesPage(): React.ReactElement {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [items, setItems] = useState<IndustryTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<IndustryTemplateDetail | null>(null);
  const [result, setResult] = useState<InstantiateResult | null>(null);
  const [instantiating, setInstantiating] = useState<string | null>(null);

  const load = async (): Promise<void> => {
    setLoading(true);
    try {
      const r = await industryTemplatesApi.list();
      setItems(r.items ?? []);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const onView = async (id: string): Promise<void> => {
    try {
      const d = await industryTemplatesApi.get(id);
      setDetail(d);
    } catch (e) {
      message.error('加载详情失败: ' + (e as Error).message);
    }
  };

  const onInstantiate = async (id: string, name: string): Promise<void> => {
    setInstantiating(id);
    try {
      const r = await industryTemplatesApi.instantiate({
        template_id: id,
        workflow_name: `${name} (${new Date().toLocaleDateString('zh-CN')})`,
      });
      setResult(r);
      message.success(
        `已实例化工作流: ${r.workflow_name} (${r.node_count} 节点 / ${r.edge_count} 边)`,
      );
      void load();
    } catch (e) {
      message.error('实例化失败: ' + (e as Error).message);
    } finally {
      setInstantiating(null);
    }
  };

  return (
    <Card
      title="行业模板市场 (Phase 6 B30)"
      extra={
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>
          刷新
        </Button>
      }
    >
      <Table<IndustryTemplate>
        rowKey="template_id"
        loading={loading}
        dataSource={items}
        pagination={false}
        columns={[
          {
            title: '行业',
            dataIndex: 'industry',
            render: (v) => (
              <Tag color="blue">{v}</Tag>
            ),
          },
          { title: '名称', dataIndex: 'name' },
          { title: '说明', dataIndex: 'description', ellipsis: true },
          { title: '节点数', dataIndex: 'node_count', width: 80 },
          { title: '目标列', dataIndex: 'target_column', width: 100 },
          { title: '模型类型', dataIndex: 'model_type', width: 140 },
          {
            title: '操作',
            width: 180,
            render: (_, r) => (
              <Space>
                <Button
                  size="small"
                  icon={<EyeOutlined />}
                  onClick={() => void onView(r.template_id)}
                >
                  预览
                </Button>
                <Button
                  size="small"
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  loading={instantiating === r.template_id}
                  onClick={() => void onInstantiate(r.template_id, r.name)}
                >
                  实例化
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title="模板详情"
        open={!!detail}
        onCancel={() => setDetail(null)}
        footer={null}
        width={700}
      >
        {detail && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="名称">{detail.name}</Descriptions.Item>
            <Descriptions.Item label="行业">{detail.industry}</Descriptions.Item>
            <Descriptions.Item label="目标列">{detail.target_column}</Descriptions.Item>
            <Descriptions.Item label="节点数">{detail.nodes.length}</Descriptions.Item>
            <Descriptions.Item label="边数">{detail.edges.length}</Descriptions.Item>
            <Descriptions.Item label="默认数据集">{detail.default_dataset}</Descriptions.Item>
            <Descriptions.Item label="评分公式">
              <code>{detail.score_formula}</code>
            </Descriptions.Item>
            <Descriptions.Item label="说明">{detail.description}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
      <Modal
        title="实例化成功"
        open={!!result}
        onCancel={() => setResult(null)}
        onOk={() => {
          if (result) navigate(`/workflows/${result.workflow_id}`);
          setResult(null);
        }}
        okText="打开工作流"
        cancelText="关闭"
      >
        {result && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Typography.Text>
              已从模板「
              <Typography.Text strong>{result.template_name}</Typography.Text>
              」一键实例化出工作流,包含 <Typography.Text strong>{result.node_count}</Typography.Text>{' '}
              个节点和 <Typography.Text strong>{result.edge_count}</Typography.Text> 条边.
            </Typography.Text>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="工作流 ID">
                <Typography.Text code>{result.workflow_id}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="工作流名称">{result.workflow_name}</Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {new Date(result.created_at).toLocaleString('zh-CN')}
              </Descriptions.Item>
            </Descriptions>
          </Space>
        )}
      </Modal>
    </Card>
  );
}

export default IndustryTemplatesPage;
