/** 告警管理 — Phase 5 B27. */
import { useEffect, useState } from 'react';
import { Card, Tabs, Table, Tag, App, Button } from 'antd';
import { ReloadOutlined, AlertOutlined, BellOutlined } from '@ant-design/icons';
import {
  alertsApi,
  type AlertRule,
  type AlertSilence,
} from '@/api/alerts';

export function AlertsPage(): React.ReactElement {
  const { message } = App.useApp();
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [silences, setSilences] = useState<AlertSilence[]>([]);

  const load = async (): Promise<void> => {
    try {
      const [r, s] = await Promise.all([
        alertsApi.listRules(),
        alertsApi.listSilences(),
      ]);
      setRules(r.items);
      setSilences(s.items);
    } catch (e) {
      message.error('加载失败: ' + (e as Error).message);
    }
  };

  useEffect(() => { void load(); }, []);

  return (
    <Tabs
      defaultActiveKey="rules"
      items={[
        {
          key: 'rules',
          label: <><AlertOutlined /> 告警规则</>,
          children: (
            <Card extra={<Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>}>
              <Table<AlertRule>
                rowKey="rule_id"
                dataSource={rules}
                pagination={false}
                columns={[
                  { title: '名称', dataIndex: 'name' },
                  { title: '表达式 (PromQL)', dataIndex: 'promql', ellipsis: true },
                  {
                    title: '严重级别',
                    dataIndex: 'severity',
                    render: (s: string) => <Tag color={s === 'critical' ? 'red' : s === 'warning' ? 'orange' : 'blue'}>{s}</Tag>,
                  },
                  { title: '持续', dataIndex: 'for_duration' },
                  {
                    title: '启用',
                    dataIndex: 'enabled',
                    render: (e: boolean) => e ? <Tag color="success">✓</Tag> : <Tag>✗</Tag>,
                  },
                ]}
              />
            </Card>
          ),
        },
        {
          key: 'silences',
          label: <><BellOutlined /> 静默规则</>,
          children: (
            <Card>
              <Table<AlertSilence>
                rowKey="silence_id"
                dataSource={silences}
                pagination={false}
                columns={[
                  { title: 'Matchers', dataIndex: 'matchers', render: (m: Array<{ key: string; value: string }>) => m.map((x) => `${x.key}=${x.value}`).join(', ') },
                  {
                    title: '开始',
                    dataIndex: 'starts_at',
                    render: (t: string) => new Date(t).toLocaleString('zh-CN'),
                  },
                  {
                    title: '结束',
                    dataIndex: 'ends_at',
                    render: (t: string) => new Date(t).toLocaleString('zh-CN'),
                  },
                  { title: '备注', dataIndex: 'comment' },
                ]}
              />
            </Card>
          ),
        },
      ]}
    />
  );
}

export default AlertsPage;