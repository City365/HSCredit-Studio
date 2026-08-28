/** 模板共享 — Phase 6 B31. */
import { useState } from 'react';
import { Card, Form, Input, Select, Button, Space, App, Tag, Table, Modal, Descriptions } from 'antd';
import { CloudUploadOutlined,  AuditOutlined } from '@ant-design/icons';
import { templateSharingApi, type TemplateReviewLog } from '@/api/template-sharing';

export function TemplateSharingPage(): React.ReactElement {
  const { message } = App.useApp();
  const [logs, setLogs] = useState<TemplateReviewLog[]>([]);
  const [logsTplId, setLogsTplId] = useState<string | null>(null);

  const onPublish = async (values: {
    workflow_id: string; template_name: string; visibility: 'private' | 'tenant' | 'public'; tags?: string[];
  }): Promise<void> => {
    try {
      const r = await templateSharingApi.publish({
        workflow_id: values.workflow_id,
        template_name: values.template_name,
        visibility: values.visibility,
        tags: values.tags,
      });
      message.success(`已发布为模板 (状态: ${r.review_status}, ${r.node_count} 节点)`);
    } catch (e) {
      message.error('发布失败: ' + (e as Error).message);
    }
  };

  const onLoadLogs = async (templateId: string): Promise<void> => {
    try {
      const r = await templateSharingApi.listLogs(templateId);
      setLogs(r.items);
      setLogsTplId(templateId);
    } catch (e) {
      message.error('加载审核日志失败: ' + (e as Error).message);
    }
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card title={<><CloudUploadOutlined /> 从工作流发布为租户模板</>}>
        <Form layout="vertical" onFinish={onPublish} style={{ maxWidth: 600 }}>
          <Form.Item name="workflow_id" label="工作流 ID" rules={[{ required: true }]}>
            <Input placeholder="UUID" />
          </Form.Item>
          <Form.Item name="template_name" label="模板名称" rules={[{ required: true, min: 1, max: 255 }]}>
            <Input placeholder="模板名称" />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="添加标签" />
          </Form.Item>
          <Form.Item name="visibility" label="可见性" initialValue="tenant">
            <Select
              options={[
                { label: '私有 (仅自己)', value: 'private' },
                { label: '租户内', value: 'tenant' },
                { label: '公开', value: 'public' },
              ]}
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">发布</Button>
          </Form.Item>
        </Form>
      </Card>

      <Card title={<><AuditOutlined /> 审核日志查询</>}>
        <Space>
          <Input.Search
            placeholder="输入模板 ID 查看审核历史"
            enterButton="查询"
            style={{ width: 400 }}
            onSearch={(v) => v && void onLoadLogs(v)}
          />
        </Space>
        {logs.length > 0 && (
          <Table<TemplateReviewLog>
            rowKey="log_id"
            dataSource={logs}
            pagination={false}
            style={{ marginTop: 16 }}
            columns={[
              { title: '模板 ID', dataIndex: 'template_id', ellipsis: true },
              { title: '审核人', dataIndex: 'reviewer_id', ellipsis: true },
              {
                title: '状态变更',
                render: (_, r) => (
                  <Space>
                    {r.old_status && <Tag>{r.old_status}</Tag>}
                    <span>→</span>
                    <Tag color={r.new_status === 'approved' ? 'success' : 'error'}>{r.new_status}</Tag>
                  </Space>
                ),
              },
              { title: '评论', dataIndex: 'comment', ellipsis: true },
              {
                title: '时间',
                dataIndex: 'created_at',
                render: (t: string) => new Date(t).toLocaleString('zh-CN'),
              },
            ]}
          />
        )}
      </Card>

      <Modal title={`审核日志 - ${logsTplId}`} open={!!logsTplId && false} footer={null}>
        {logs.length > 0 && (
          <Descriptions column={1} bordered>
            <Descriptions.Item label="日志条数">{logs.length}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </Space>
  );
}

export default TemplateSharingPage;