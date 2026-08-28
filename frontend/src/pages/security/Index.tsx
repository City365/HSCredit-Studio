/** 安全运营中心 — Phase 5 B25. */
import { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Tag, Tabs, Space, App, Button, Descriptions } from 'antd';
import {
  ReloadOutlined,
  SafetyCertificateOutlined,
  LinkOutlined,
  GlobalOutlined,
} from '@ant-design/icons';
import { securityApi, type SecurityMetrics } from '@/api/security';

export function SecurityPage(): React.ReactElement {
  const { message } = App.useApp();
  const [metrics, setMetrics] = useState<SecurityMetrics | null>(null);
  const [chainStatus, setChainStatus] = useState<{ status: string; checkpoints: number } | null>(null);

  const load = async (): Promise<void> => {
    try {
      const m = await securityApi.metrics();
      setMetrics(m);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    }
  };

  useEffect(() => { void load(); }, []);

  const onCheckChain = async (): Promise<void> => {
    try {
      const r = await securityApi.checkChain({});
      setChainStatus({ status: r.status, checkpoints: r.checkpoints_checked });
      message[r.status === 'valid' ? 'success' : 'error'](
        `链完整性: ${r.status} (检查 ${r.checkpoints_checked} 节点)`,
      );
    } catch (e) {
      message.error('链检查失败: ' + (e as Error).message);
    }
  };

  return (
    <Tabs
      defaultActiveKey="overview"
      items={[
        {
          key: 'overview',
          label: <><SafetyCertificateOutlined /> 安全总览</>,
          children: (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <Card extra={<Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>}>
                {metrics && (
                  <Row gutter={16}>
                    <Col span={4}><Statistic title="审计事件" value={metrics.total_audit_events} /></Col>
                    <Col span={4}><Statistic title="24h 登录失败" value={metrics.failed_logins_24h} /></Col>
                    <Col span={4}><Statistic title="活跃锁定" value={metrics.active_lockouts} /></Col>
                    <Col span={4}><Statistic title="未关漏洞" value={metrics.open_vulnerabilities} /></Col>
                    <Col span={4}><Statistic title="IP 规则" value={metrics.ip_rules_count} /></Col>
                    <Col span={4}>
                      <Statistic
                        title="审计链"
                        valueRender={() => (
                          <Tag color={metrics.chain_integrity === 'valid' ? 'success' : 'error'}>
                            {metrics.chain_integrity}
                          </Tag>
                        )}
                      />
                    </Col>
                  </Row>
                )}
              </Card>
              <Card title="审计链完整性 (HMAC)" extra={<Button onClick={() => void onCheckChain()}>手动校验</Button>}>
                {chainStatus && (
                  <Descriptions column={2} bordered>
                    <Descriptions.Item label="状态">
                      <Tag color={chainStatus.status === 'valid' ? 'success' : 'error'}>
                        {chainStatus.status}
                      </Tag>
                    </Descriptions.Item>
                    <Descriptions.Item label="校验节点数">{chainStatus.checkpoints}</Descriptions.Item>
                  </Descriptions>
                )}
              </Card>
            </Space>
          ),
        },
        {
          key: 'siem',
          label: <><LinkOutlined /> SIEM 导出</>,
          children: (
            <Card>
              <p>SIEM 审计日志导出 (CEF / LEEF / JSON 格式)</p>
              <Button
                onClick={async () => {
                  try {
                    await securityApi.exportSiem({ format: 'json' });
                    message.success('导出已触发');
                  } catch (e) {
                    message.error('导出失败: ' + (e as Error).message);
                  }
                }}
              >
                导出 (JSON)
              </Button>
            </Card>
          ),
        },
        {
          key: 'waf',
          label: <><GlobalOutlined /> WAF 入侵检测</>,
          children: (
            <Card>
              <p>测试请求体是否触发 WAF 规则:</p>
              <Button
                danger
                onClick={async () => {
                  try {
                    const r = await securityApi.intrusionCheck({
                      payload: "' OR '1'='1 -- <script>alert(1)</script>",
                      source_ip: '203.0.113.42',
                    });
                    if (r.blocked) {
                      message.warning(`已拦截: ${r.threats.length} 个威胁`);
                    } else {
                      message.success('未检测到威胁');
                    }
                  } catch (e) {
                    message.error('检测失败: ' + (e as Error).message);
                  }
                }}
              >
                测试 SQL/XSS 注入
              </Button>
            </Card>
          ),
        },
      ]}
    />
  );
}

export default SecurityPage;