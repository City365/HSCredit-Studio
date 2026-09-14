/** 试运行页面 — 占位 (阶段 7 完整实现). */

import { useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  InputNumber,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import { PlayCircleOutlined } from '@ant-design/icons';
import { App } from 'antd';
import { useApiMutation, useApiQuery } from '@/hooks/useApi';
import { customNodesApi } from '@/api/custom-nodes';
import type { TestRunResponse } from '@/api/custom-nodes';

export default function NodesTestPage(): React.ReactElement {
  const { id } = useParams<{ id: string }>();
  const { message } = App.useApp();
  const [result, setResult] = useState<TestRunResponse | null>(null);
  const [form] = Form.useForm();

  const nodeQuery = useApiQuery(
    ['custom-node', id ?? ''],
    () => customNodesApi.get(id ?? ''),
    id ?? '',
  );

  const testMutation = useApiMutation<TestRunResponse, { code: string; x: number }>(
    (vars) =>
      customNodesApi.testRun(id ?? '', {
        sample_inputs: {},
        sample_params: { x: vars.x },
        sample_data: { code: vars.code },
      }),
  );

  const onRun = async () => {
    try {
      const values = await form.validateFields();
      const res = await testMutation.mutateAsync(values);
      setResult(res);
      if (res.status === 'success') {
        message.success(`执行成功 (${res.duration_ms}ms)`);
      } else {
        message.warning(`执行: ${res.status}`);
      }
    } catch (e) {
      message.error(`试运行失败: ${(e as Error).message}`);
    }
  };

  if (nodeQuery.isLoading) {
    return <Spin size="large" />;
  }
  if (nodeQuery.isError || !nodeQuery.data) {
    return <Empty description="节点加载失败" />;
  }

  const cn = nodeQuery.data;

  return (
    <Card
      title={
        <Space>
          <PlayCircleOutlined />
          试运行: {cn.icon} {cn.name}
          <Tag color="orange">{cn.node_type}</Tag>
          <Tag>v{cn.current_version_number}</Tag>
        </Space>
      }
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ x: 5 }}
      >
        <Form.Item
          name="code"
          label="代码 (用于试运行的 user code, 默认与节点当前 code 一致)"
          tooltip="如需测试不同代码可粘贴在这里; 留空使用节点最新 code"
        >
          <Input.TextArea rows={4} placeholder="留空使用节点当前 code" />
        </Form.Item>
        <Form.Item name="x" label="参数 x (sample_params.x)">
          <InputNumber />
        </Form.Item>
        <Form.Item>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={testMutation.isPending}
            onClick={onRun}
          >
            运行试运行
          </Button>
        </Form.Item>
      </Form>

      {result && (
        <Card type="inner" title={`结果 (status=${result.status}, duration=${result.duration_ms}ms)`}>
          {result.error && (
            <Alert
              type="error"
              message={`错误: ${result.error.code}`}
              description={String(result.error.message ?? '')}
              style={{ marginBottom: 12 }}
            />
          )}
          {result.outputs && (
            <>
              <Typography.Title level={5}>Outputs</Typography.Title>
              <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 4 }}>
                {JSON.stringify(result.outputs, null, 2)}
              </pre>
            </>
          )}
          {result.resource_usage && (
            <>
              <Typography.Title level={5}>资源用量</Typography.Title>
              <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 4 }}>
                {JSON.stringify(result.resource_usage, null, 2)}
              </pre>
            </>
          )}
          {result.logs && result.logs.length > 0 && (
            <>
              <Typography.Title level={5}>日志</Typography.Title>
              <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 4 }}>
                {result.logs.join('\n')}
              </pre>
            </>
          )}
        </Card>
      )}
    </Card>
  );
}
