/** 配额与用量 — Phase 4 B18/B19. */
import { useEffect, useState } from 'react';
import { Card, Row, Col, Progress, Statistic, Tag, Space, App, Button } from 'antd';
import { ReloadOutlined, DashboardOutlined } from '@ant-design/icons';
import { quotaApi, type QuotaUsage } from '@/api/quota';
import { usageApi, type TenantUsage } from '@/api/quota';

export function QuotaPage(): React.ReactElement {
  const { message } = App.useApp();
  const [quota, setQuota] = useState<QuotaUsage | null>(null);
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

  useEffect(() => { void load(); }, []);

  const pct = (used: number, limit: number): number =>
    limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card title={<><DashboardOutlined /> 当前用量 vs 配额</>} extra={<Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>}>
        {quota && (
          <Row gutter={16}>
            <Col span={8}>
              <Card type="inner" title="月度 Run">
                <Statistic
                  value={quota.monthly_runs_used}
                  suffix={`/ ${quota.monthly_runs_limit}`}
                />
                <Progress percent={pct(quota.monthly_runs_used, quota.monthly_runs_limit)} status={quota.ratio > 0.8 ? 'exception' : 'normal'} />
              </Card>
            </Col>
            <Col span={8}>
              <Card type="inner" title="Sandbox 时长 (ms)">
                <Statistic
                  value={quota.monthly_duration_ms_used}
                  suffix={`/ ${quota.monthly_duration_ms_limit}`}
                />
                <Progress percent={pct(quota.monthly_duration_ms_used, quota.monthly_duration_ms_limit)} />
              </Card>
            </Col>
            <Col span={8}>
              <Card type="inner" title="存储 (bytes)">
                <Statistic
                  value={quota.monthly_storage_bytes_used}
                  suffix={`/ ${(quota.monthly_storage_gb_limit * 1024 ** 3).toFixed(0)}`}
                />
                <Progress percent={pct(quota.monthly_storage_bytes_used, quota.monthly_storage_gb_limit * 1024 ** 3)} />
              </Card>
            </Col>
          </Row>
        )}
      </Card>

      {usage && (
        <Card title="聚合用量">
          <Row gutter={16}>
            <Col span={6}><Statistic title="Run 总数" value={usage.runs} /></Col>
            <Col span={6}><Statistic title="时长 (ms)" value={usage.duration_ms} /></Col>
            <Col span={6}><Statistic title="存储 (bytes)" value={usage.storage_bytes} /></Col>
            <Col span={6}><Statistic title="API 调用" value={usage.api_calls} /></Col>
          </Row>
          {Object.keys(usage.by_node_type).length > 0 && (
            <Card type="inner" title="按节点类型" style={{ marginTop: 16 }}>
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