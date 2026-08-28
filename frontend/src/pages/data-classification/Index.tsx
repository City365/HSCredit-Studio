/** 数据脱敏 — Phase 5 B24. */
import { useEffect, useState } from 'react';
import { Card, Table, Tag, Space, App, Form, Input, Button, Descriptions } from 'antd';
import { LockOutlined, ExperimentOutlined } from '@ant-design/icons';
import { dataClassificationApi, type FieldClassification } from '@/api/data-classification';

export function DataClassificationPage(): React.ReactElement {
  const { message } = App.useApp();
  const [fields, setFields] = useState<FieldClassification[]>([]);
  const [redactResult, setRedactResult] = useState<{ redacted: Record<string, string>; masked_fields: string[] } | null>(null);

  const load = async (): Promise<void> => {
    try {
      const r = await dataClassificationApi.listFields();
      setFields(r.items);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    }
  };

  useEffect(() => { void load(); }, []);

  const onRedact = async (values: { payload: string; fields?: string }): Promise<void> => {
    try {
      const payload = JSON.parse(values.payload) as Record<string, unknown>;
      const r = await dataClassificationApi.redact({
        payload,
        fields: values.fields ? values.fields.split(',').map((s) => s.trim()) : undefined,
      });
      setRedactResult(r);
      message.success(`脱敏完成: ${r.masked_fields.length} 个字段`);
    } catch (e) {
      message.error('脱敏失败: ' + (e as Error).message);
    }
  };

  const onHash = async (values: { value: string; field: string }): Promise<void> => {
    try {
      const r = await dataClassificationApi.hashField(values);
      message.success(`${r.field} hash: ${r.hash.slice(0, 16)}...`);
    } catch (e) {
      message.error('Hash 失败: ' + (e as Error).message);
    }
  };

  const levelColors: Record<string, string> = {
    public: 'default',
    internal: 'blue',
    sensitive: 'orange',
    high_sensitive: 'red',
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card title="字段分级 (Phase 5 B24)">
        <Table<FieldClassification>
          rowKey="field_name"
          dataSource={fields}
          pagination={{ pageSize: 30 }}
          columns={[
            { title: '字段名', dataIndex: 'field_name' },
            {
              title: '级别',
              dataIndex: 'level',
              render: (l: string) => <Tag color={levelColors[l] ?? 'default'}>{l}</Tag>,
            },
            { title: '正则', dataIndex: 'pattern', ellipsis: true },
          ]}
        />
      </Card>

      <Card title={<><ExperimentOutlined /> 脱敏测试</>}>
        <Form layout="vertical" onFinish={onRedact} style={{ maxWidth: 600 }}>
          <Form.Item name="payload" label="Payload (JSON)" rules={[{ required: true }]}>
            <Input.TextArea
              rows={3}
              placeholder='{"name":"张三","id_card":"110101199003078812","phone":"13800138000"}'
            />
          </Form.Item>
          <Form.Item name="fields" label="指定脱敏字段 (留空 = 全部敏感字段)">
            <Input placeholder="id_card,phone" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" icon={<LockOutlined />} htmlType="submit">
              脱敏
            </Button>
          </Form.Item>
        </Form>
        {redactResult && (
          <Descriptions column={1} bordered style={{ marginTop: 16 }} title="脱敏结果">
            <Descriptions.Item label="脱敏字段">
              {redactResult.masked_fields.map((f) => <Tag key={f} color="orange">{f}</Tag>)}
            </Descriptions.Item>
            <Descriptions.Item label="脱敏后">
              <pre style={{ background: '#f5f5f5', padding: 8 }}>
                {JSON.stringify(redactResult.redacted, null, 2)}
              </pre>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Card>

      <Card title={<><LockOutlined /> 字段 hash</>}>
        <Form layout="inline" onFinish={onHash}>
          <Form.Item name="field" rules={[{ required: true }]}>
            <Input placeholder="字段名" style={{ width: 160 }} />
          </Form.Item>
          <Form.Item name="value" rules={[{ required: true }]}>
            <Input placeholder="原始值" style={{ width: 220 }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">
              计算 hash
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </Space>
  );
}

export default DataClassificationPage;