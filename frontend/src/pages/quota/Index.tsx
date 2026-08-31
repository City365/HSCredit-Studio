/** 配额与用量 — Phase 4 B18/B19.
展示月度配额使用 + 实时校验状态.
*/
import { useEffect, useState } from 'react';
import { Card, Row, Col, Progress, Statistic, Tag, Space, App, Button, Alert, Descriptions } from 'antd';
import { ReloadOutlined, DashboardOutlined, ThunderboltOutlined, DatabaseOutlined, ApiOutlined } from '@ant-design/icons';
import { quotaApi, type QuotaResponse, usageApi, type TenantUsage } from '@/api/quota';

export function QuotaPage(): React.ReactElement {
  const { message } = App.useApp();
  const [quota, setQuota] = useState<QuotaResponse | null>(null);
  const [usage, setUsage] = useState<TenantUsage | null>(null);

  const load = async (): Promise<void> => {
    try {
      const [q, u] = await Promise.all([quotaApi.get(), usageApi.get()]);
      setQuota(q);
      setUsage(u);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const pct = (v: { ratio: number; used: number; limit: number }): number =>
    Math.round(v.ratio * 100);

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {/* 配额状态卡 (顶部) */}
      {quota && (
        <Card
          title={
            <Space>
              <DashboardOutlined />
              <span>月度配额 (计划: {quota.snapshot.plan})</span>
              {quota.check.allowed ? (
                <Tag color="success">✓ {quota.check.message}</Tag>
              ) : (
                <Tag color="error">✗ {quota.check.message}</Tag>
              )}
            </Space>
          }
          extra={<Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>}
        >
          {quota.check.near_limit && (
            <Alert
              type="warning"
              showIcon
              message="用量接近限额"
              description="建议升级订阅或清理资源, 避免触发硬限流"
              style={{ marginBottom: 16 }}
            />
          )}
          <Row gutter={16}>
            <Col span={8}>
              <Card type="inner" title={<><ThunderboltOutlined /> 月度 Run</>}>
                <Statistic
                  value={quota.snapshot.monthly_runs.used}
                  suffix={`/ ${quota.snapshot.monthly_runs.limit}`}
                />
                <Progress
                  percent={pct(quota.snapshot.monthly_runs)}
                  status={quota.snapshot.monthly_runs.ratio > 0.8 ? 'exception' : 'normal'}
                />
                <Tag>{Math.round(quota.snapshot.monthly_runs.ratio * 100)}% 已用</Tag>
              </Card>
            </Col>
            <Col span={8}>
              <Card type="inner" title={<><ApiOutlined /> Sandbox 时长 (秒)</>}>
                <Statistic
                  value={Math.round(quota.snapshot.monthly_duration_ms.used / 1000)}
                  suffix={`/ ${Math.round(quota.snapshot.monthly_duration_ms.limit / 1000)}`}
                />
                <Progress
                  percent={pct(quota.snapshot.monthly_duration_ms)}
                  status={quota.snapshot.monthly_duration_ms.ratio > 0.8 ? 'exception' : 'normal'}
                />
                <Tag>{Math.round(quota.snapshot.monthly_duration_ms.ratio * 100)}% 已用</Tag>
              </Card>
            </Col>
            <Col span={8}>
              <Card type="inner" title={<><DatabaseOutlined /> 存储 (GB)</>}>
                <Statistic
                  value={quota.snapshot.monthly_storage_gb.used.toFixed(2)}
                  suffix={`/ ${quota.snapshot.monthly_storage_gb.limit.toFixed(0)}`}
                />
                <Progress
                  percent={pct(quota.snapshot.monthly_storage_gb)}
                  status={quota.snapshot.monthly_storage_gb.ratio > 0.8 ? 'exception' : 'normal'}
                />
                <Tag>{Math.round(quota.snapshot.monthly_storage_gb.ratio * 100)}% 已用</Tag>
              </Card>
            </Col>
          </Row>
        </Card>
      )}

      {/* 实时校验 */}
      {quota && (
        <Card title="实时配额校验">
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="校验结果">
              {quota.check.allowed ? <Tag color="success">✓ ALLOWED</Tag> : <Tag color="error">✗ DENIED</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="接近限额">
              {quota.check.near_limit ? <Tag color="warning">⚠ NEAR LIMIT</Tag> : <Tag color="default">正常</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="超限维度" span={2}>
              {quota.check.exceeded_dim ?? '无'}
            </Descriptions.Item>
            <Descriptions.Item label="提示信息" span={2}>
              {quota.check.message}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      {/* 聚合用量 */}
      {usage && (
        <Card title="本月聚合用量">
          <Row gutter={16}>
            <Col span={6}><Statistic title="Run 总数" value={usage.runs} /></Col>
            <Col span={6}><Statistic title="累计时长" value={`${(usage.duration_ms / 1000).toFixed(1)} 秒`} /></Col>
            <Col span={6}><Statistic title="累计存储" value={`${(usage.storage_bytes / 1024 / 1024).toFixed(2)} MB`} /></Col>
            <Col span={6}><Statistic title="API 调用" value={usage.api_calls} /></Col>
          </Row>
          {Object.keys(usage.by_node_type ?? {}).length > 0 && (
            <Card type="inner" title="按节点类型分布" style={{ marginTop: 16 }}>
              {Object.entries(usage.by_node_type).map(([k, v]) => (
                <Tag key={k} color="blue" style={{ margin: 4 }}>
                  {k}: {v}
                </Tag>
              ))}
            </Card>
          )}
        </Card>
      )}
    </Space>
  );
}

export default QuotaPage;