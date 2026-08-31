/** 安全运营中心 — Phase 5 B25.

包含: SOC 总览指标 + 审计链完整性 + SIEM 导出 + WAF 入侵检测 + IP 规则 + 漏洞跟踪.
*/
import { useEffect, useState } from 'react';
import {
  Card,
  Row,
  Col,
  Statistic,
  Tag,
  Tabs,
  Space,
  App,
  Button,
  Descriptions,
  Alert,
  List,
  Typography,
} from 'antd';
import {
  ReloadOutlined,
  SafetyCertificateOutlined,
  LinkOutlined,
  GlobalOutlined,
  BugOutlined,
} from '@ant-design/icons';
import { securityApi, type SecurityMetrics } from '@/api/security';

const { Text } = Typography;

export function SecurityPage(): React.ReactElement {
  const { message } = App.useApp();
  const [metrics, setMetrics] = useState<SecurityMetrics | null>(null);
  const [chainStatus, setChainStatus] = useState<{ status: string; checkpoints: number } | null>(null);
  const [wafDemo, setWafDemo] = useState<{ blocked: boolean; threats: Array<{ rule: string; severity: string }> } | null>(null);

  const load = async (): Promise<void> => {
    try {
      const m = await securityApi.metrics();
      setMetrics(m);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const onCheckChain = async (): Promise<void> => {
    try {
      const r = await securityApi.checkChain({});
      setChainStatus({ status: r.status, checkpoints: r.checkpoints_checked });
      message[r.status === 'valid' ? 'success' : 'error'](
        `审计链: ${r.status} (校验 ${r.checkpoints_checked} 个节点)`,
      );
    } catch (e) {
      message.error('链检查失败: ' + (e as Error).message);
    }
  };

  const onWafTest = async (payload: string): Promise<void> => {
    try {
      const r = await securityApi.intrusionCheck({ payload, source_ip: '203.0.113.42' });
      setWafDemo(r);
      if (r.blocked) {
        message.warning(`WAF 拦截: ${r.threats.length} 个威胁`);
      } else {
        message.success('未检测到威胁');
      }
    } catch (e) {
      message.error('WAF 测试失败: ' + (e as Error).message);
    }
  };

  const onSiemExport = async (format: 'json' | 'cef' | 'leef'): Promise<void> => {
    try {
      await securityApi.exportSiem({ format });
      message.success(`SIEM 导出已触发 (${format.toUpperCase()})`);
    } catch (e) {
      message.error('SIEM 导出失败: ' + (e as Error).message);
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
              {/* 顶部 6 指标卡 */}
              <Card extra={<Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>}>
                {metrics ? (
                  <Row gutter={16}>
                    <Col span={4}>
                      <Statistic title="审计事件总数" value={metrics.total_events ?? 0} />
                    </Col>
                    <Col span={4}>
                      <Statistic title="登录失败" value={metrics.failed_logins ?? 0} />
                    </Col>
                    <Col span={4}>
                      <Statistic title="鉴权失败" value={metrics.auth_failures ?? 0} />
                    </Col>
                    <Col span={4}>
                      <Statistic title="敏感数据访问" value={metrics.sensitive_data_access ?? 0} />
                    </Col>
                    <Col span={4}>
                      <Statistic title="数据导出" value={metrics.data_exports ?? 0} />
                    </Col>
                    <Col span={4}>
                      <Statistic title="开放漏洞" value={metrics.open_vulnerabilities ?? 0} />
                    </Col>
                  </Row>
                ) : (
                  <Alert type="info" message="加载中..." />
                )}
              </Card>

              {/* Top actions + Top IPs */}
              {metrics && (
                <Row gutter={16}>
                  <Col span={12}>
                    <Card title="Top 操作 (Top 10)">
                      <List
                        size="small"
                        dataSource={(metrics.top_actions ?? []).slice(0, 10)}
                        renderItem={(item: [string, number], idx) => (
                          <List.Item>
                            <span style={{ width: 28 }}>#{idx + 1}</span>
                            <Tag>{item[0]}</Tag>
                            <span style={{ marginLeft: 'auto', fontWeight: 600 }}>{item[1]} 次</span>
                          </List.Item>
                        )}
                      />
                      {(!metrics.top_actions || metrics.top_actions.length === 0) && (
                        <Text type="secondary">暂无审计事件</Text>
                      )}
                  </Card>
                  </Col>
                  <Col span={12}>
                    <Card title="Top IP (Top 10)">
                      <List
                        size="small"
                        dataSource={(metrics.top_ips ?? []).slice(0, 10)}
                        renderItem={(item, idx) => (
                          <List.Item>
                            <span style={{ width: 28 }}>#{idx + 1}</span>
                            <code>{item[0]}</code>
                            <span style={{ marginLeft: 'auto', fontWeight: 600 }}>{item[1]} 次</span>
                          </List.Item>
                        )}
                      />
                      {(!metrics.top_ips || metrics.top_ips.length === 0) && (
                        <Text type="secondary">无 IP 记录 (演示环境 IP 通常匿名)</Text>
                      )}
                    </Card>
                  </Col>
                </Row>
              )}

              {/* 审计链验证 */}
              <Card
                title={<><SafetyCertificateOutlined /> 审计链完整性 (HMAC-SHA256)</>}
                extra={<Button type="primary" onClick={() => void onCheckChain()}>手动校验</Button>}
              >
                  <Descriptions column={2} bordered size="small">
                    <Descriptions.Item label="链状态">
                      {chainStatus ? (
                        <Tag color={chainStatus.status === 'valid' ? 'success' : 'error'}>
                          {chainStatus.status}
                        </Tag>
                      ) : (
                        <Text type="secondary">点击右侧按钮开始校验</Text>
                      )}
                    </Descriptions.Item>
                    <Descriptions.Item label="校验节点数">
                      {chainStatus?.checkpoints ?? '—'}
                    </Descriptions.Item>
                    <Descriptions.Item label="说明" span={2}>
                      审计事件通过 HMAC-SHA256 链式哈希, 任何篡改都会导致链验证失败。等保三级硬要求。
                    </Descriptions.Item>
                  </Descriptions>
                </Card>
            </Space>
          ),
        },
        {
          key: 'waf',
          label: <><GlobalOutlined /> WAF 入侵检测</>,
          children: (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <Card>
                <p>模拟攻击 payload, 验证 WAF 28 模式规则拦截能力:</p>
                <Space wrap>
                  <Button danger onClick={() => void onWafTest("' OR '1'='1 -- ")}>
                    测试 SQL 注入
                  </Button>
                  <Button danger onClick={() => void onWafTest("<script>alert('xss')</script>")}>
                    测试 XSS
                  </Button>
                  <Button danger onClick={() => void onWafTest("../../../etc/passwd")}>
                    测试路径穿越
                  </Button>
                  <Button onClick={() => void onWafTest("Hello World")}>
                    测试正常请求
                  </Button>
                </Space>
              </Card>
              {wafDemo && (
                <Card title="WAF 检测结果">
                  {wafDemo.blocked ? (
                    <Alert
                      type="error"
                      showIcon
                      message={`✗ 已拦截 (${wafDemo.threats.length} 个威胁)`}
                      description={
                        <List
                          size="small"
                          dataSource={wafDemo.threats}
                          renderItem={(item, idx) => (
                            <List.Item>
                              <span style={{ width: 28 }}>#{idx + 1}</span>
                              <Tag color="red">{item.severity}</Tag>
                              <code>{item.rule}</code>
                            </List.Item>
                          )}
                        />
                      }
                    />
                  ) : (
                    <Alert type="success" showIcon message="✓ 未检测到威胁, 请求正常" />
                  )}
                </Card>
              )}
            </Space>
          ),
        },
        {
          key: 'siem',
          label: <><LinkOutlined /> SIEM 导出</>,
          children: (
            <Card>
              <p>导出审计日志到外部 SIEM 系统 (Splunk / QRadar / Elastic):</p>
              <Space wrap>
                <Button onClick={() => void onSiemExport('json')}>导出 JSON</Button>
                <Button onClick={() => void onSiemExport('cef')}>导出 CEF (ArcSight)</Button>
                <Button onClick={() => void onSiemExport('leef')}>导出 LEEF (QRadar)</Button>
              </Space>
              <p style={{ marginTop: 16, color: '#666', fontSize: 12 }}>
                格式说明: CEF = Common Event Format (ArcSight), LEEF = Log Event Extended Format (QRadar), JSON = 通用结构化日志.
              </p>
            </Card>
          ),
        },
        {
          key: 'vuln',
          label: <><BugOutlined /> 漏洞跟踪</>,
          children: (
            <Card>
              <p>漏洞跟踪 (当前 0 开放) — 演示环境无生产漏洞, 真实环境接入漏洞扫描器 (OWASP ZAP / Nessus / Snyk).</p>
              <Button onClick={() => message.info('演示环境无此功能, 真实环境可录入漏洞跟踪')}>
                登记新漏洞
              </Button>
            </Card>
          ),
        },
      ]}
    />
  );
}

export default SecurityPage;