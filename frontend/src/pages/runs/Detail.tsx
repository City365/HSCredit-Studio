/**
 * Run 详情页 — 总览 + 节点执行时间线 + 实时日志流 + 重试按钮.
 *
 * 设计要点:
 *   - 通过 useWebSocket 订阅 /ws/run/{runId}，实时更新进度与节点状态
 *   - 维护 liveLogs 状态数组，按时间顺序追加 WS log 事件
 *   - 日志按 stream 分色（stdout 灰、stderr 红、system 蓝），便于定位错误
 *   - 节点状态右侧根据 ne.status 渲染「重试」按钮（仅 failed 可点击）
 *   - error_code 通过 ERROR_CODE_MESSAGES 字典映射为中文
 */

import { useState, useMemo, useRef, useEffect } from 'react';
import {
  Card,
  Descriptions,
  Tag,
  Progress,
  Timeline,
  Empty,
  Space,
  Typography,
  Button,
  message as antdMessage,
  Tooltip,
} from 'antd';
import {
  ReloadOutlined,
  ClearOutlined,
  DownloadOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import { runsApi } from '@/api/runs';
import { useApiQuery, useApiMutation } from '@/hooks/useApi';
import { useWebSocket } from '@/hooks/useWebSocket';
import { ArtifactViewer } from '@/components/ArtifactViewer';
import type {
  LogEvent,
  NodeExecution,
  NodeExecutionEvent,
  NodeExecutionStatus,
  RunStatus,
  RunStatusEvent,
  WSEvent,
  NodeExecution as NodeExecutionType,
} from '@/types';
import { ERROR_CODE_MESSAGES } from '@/types';

const STATUS_COLOR: Record<string, string> = {
  pending: 'default',
  queued: 'default',
  running: 'processing',
  cached: 'success',
  cached_hit: 'success',
  success: 'success',
  failed: 'error',
  cancelled: 'default',
  retrying: 'warning',
  failed_retry: 'warning',
  skipped: 'default',
};

const STREAM_COLOR: Record<string, string> = {
  stdout: '#666',
  stderr: '#ff4d4f',
  system: '#1677ff',
};

const STREAM_LABEL: Record<string, string> = {
  stdout: 'STDOUT',
  stderr: 'STDERR',
  system: 'SYSTEM',
};

const MAX_LOGS = 500; // 防止内存爆炸；超出截断最早记录

function formatTs(ts: number | string | undefined): string {
  if (!ts) return '';
  if (typeof ts === 'number') {
    const d = new Date(ts);
    return d.toLocaleTimeString('zh-CN', { hour12: false });
  }
  // ISO 字符串
  try {
    return new Date(ts).toLocaleTimeString('zh-CN', { hour12: false });
  } catch {
    return String;
  }
}

export default function RunDetailPage() {
  const { id } = useParams<{ id: string }>();

  const [liveProgress, setLiveProgress] = useState<number>(0);
  const [liveNodeStatuses, setLiveNodeStatuses] = useState<Record<string, string>>({});
  const [liveLogs, setLiveLogs] = useState<LogEvent[]>([]);
  const logsEndRef = useRef<HTMLDivElement | null>(null);

  const { data: run, refetch: refetchRun } = useApiQuery(['run', id], runsApi.get, id ?? '');
  const { data: nodeExecs, refetch: refetchNodes } = useApiQuery(
    ['run', id, 'nodes'],
    runsApi.listNodeExecutions,
    id ?? '',
  );

  // 自动滚动到最新日志
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [liveLogs.length]);

  // WebSocket URL — 通过 Vite proxy 转发 /ws 到后端
  const wsUrl = useMemo<string | null>(
    () => (id ? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/run/${id}` : null),
    [id],
  );

  useWebSocket({
    url: wsUrl,
    onMessage: (event: WSEvent) => {
      if (event.type === 'run_status') {
        const e = event as RunStatusEvent;
        if (typeof e.progress === 'number') setLiveProgress(e.progress);
        void refetchRun();
      } else if (event.type === 'node_execution') {
        const e = event as NodeExecutionEvent;
        setLiveNodeStatuses((prev) => ({ ...prev, [e.node_id]: e.status }));
        void refetchNodes();
      } else if (event.type === 'log') {
        const e = event as LogEvent;
        setLiveLogs((prev) => {
          const next = [...prev, e];
          return next.length > MAX_LOGS ? next.slice(next.length - MAX_LOGS) : next;
        });
      }
    },
  });

  // 重试 mutation
  const retryMutation = useApiMutation(
    async (neId: string) => {
      if (!id) throw new Error('runId 缺失');
      return await runsApi.retry(id, neId);
    },
    {
      onSuccess: (resp) => {
        antdMessage.success(resp.message || '已重新入队');
        setLiveNodeStatuses((prev) => ({ ...prev, [resp.node_exec_id]: resp.status }));
        void refetchNodes();
        void refetchRun();
      },
      onError: (err: Error) => antdMessage.error(`重试失败：${err.message}`),
    },
  );

  const overallStatus: RunStatus = (run?.status as RunStatus | undefined) ?? 'pending';
  const progress = liveProgress || (run?.progress ?? 0);

  const exportLogs = (): void => {
    if (liveLogs.length === 0) {
      antdMessage.info('暂无可导出的日志');
      return;
    }
    const text = liveLogs
      .map((l) => {
        const ts = formatTs(l.ts);
        const level = l.level ? `[${l.level.toUpperCase()}]` : '';
        return `${ts} ${STREAM_LABEL[l.stream] || l.stream} ${level} ${l.node_id ? `[${l.node_id}] ` : ''}${l.message}`;
      })
      .join('\n');
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `run-${id}-logs-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.log`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <Card
        title={
          <Space>
            <Typography.Text strong>Run #{run?.run_number ?? '-'}</Typography.Text>
            <Tag color={STATUS_COLOR[overallStatus] ?? 'default'}>{overallStatus}</Tag>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Descriptions column={3} size="small">
          <Descriptions.Item label="状态">
            <Tag color={STATUS_COLOR[overallStatus] ?? 'default'}>{overallStatus}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="进度">
            <Progress percent={Math.round(progress * 100)} size="small" />
          </Descriptions.Item>
          <Descriptions.Item label="耗时">
            {run?.duration_seconds != null ? `${run.duration_seconds.toFixed(1)}s` : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="提交时间">{run?.submitted_at ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="开始时间">{run?.started_at ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="结束时间">{run?.finished_at ?? '-'}</Descriptions.Item>
          {run?.error_summary ? (
            <Descriptions.Item label="错误" span={3}>
              <span style={{ color: 'red' }}>{run.error_summary}</span>
            </Descriptions.Item>
          ) : null}
        </Descriptions>
      </Card>

      <Card
        title="节点执行"
        style={{ marginBottom: 16 }}
        extra={
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            失败节点可单独重试（不会清空已成功的上游产物）
          </Typography.Text>
        }
      >
        {nodeExecs && nodeExecs.length > 0 ? (
          <Timeline
            items={(nodeExecs as NodeExecutionType[]).map((ne) => {
              const liveStatus = (liveNodeStatuses[ne.node_id] ?? ne.status) as NodeExecutionStatus;
              const statusColor = STATUS_COLOR[liveStatus] ?? 'default';
              const timelineColor =
                statusColor === 'error'
                  ? 'red'
                  : statusColor === 'success'
                    ? 'green'
                    : statusColor === 'processing'
                      ? 'blue'
                      : 'gray';
              const errCode = (ne.error as Record<string, unknown> | null)?.code as string | undefined;
              const errMsgZh = errCode ? (ERROR_CODE_MESSAGES[errCode] ?? errCode) : null;
              return {
                color: timelineColor,
                children: (
                  <Space size="middle" wrap>
                    <span>
                      <strong>{ne.node_id}</strong> ({ne.node_type}) —{' '}
                      <Tag color={statusColor}>{liveStatus}</Tag>
                      {ne.duration_seconds != null ? (
                        <span style={{ marginLeft: 8, color: '#999' }}>
                          {ne.duration_seconds.toFixed(2)}s
                        </span>
                      ) : null}
                      {errMsgZh ? (
                        <Tooltip title={errCode}>
                          <Tag color="error" style={{ marginLeft: 8 }}>{errMsgZh}</Tag>
                        </Tooltip>
                      ) : null}
                    </span>
                    <Tooltip title={liveStatus === 'failed' ? '重试该节点' : '仅失败节点可重试'}>
                      <Button
                        size="small"
                        icon={<ReloadOutlined />}
                        disabled={liveStatus !== 'failed'}
                        loading={
                          retryMutation.isPending &&
                          retryMutation.variables === ne.id
                        }
                        onClick={() => retryMutation.mutate(ne.id)}
                      >
                        重试
                      </Button>
                    </Tooltip>
                  </Space>
                ),
              };
            })}
          />
        ) : (
          <Empty description="暂无节点执行" />
        )}
      </Card>

      <Card
        title={
          <Space>
            <FileTextOutlined />
            <span>实时日志</span>
            <Tag>{liveLogs.length}</Tag>
          </Space>
        }
        style={{ marginBottom: 16 }}
        extra={
          <Space>
            <Button
              size="small"
              icon={<ClearOutlined />}
              disabled={liveLogs.length === 0}
              onClick={() => setLiveLogs([])}
            >
              清空
            </Button>
            <Button
              size="small"
              icon={<DownloadOutlined />}
              disabled={liveLogs.length === 0}
              onClick={exportLogs}
            >
              导出
            </Button>
          </Space>
        }
        bodyStyle={{ padding: 0 }}
      >
        <div
          data-testid="live-logs"
          style={{
            maxHeight: 360,
            overflowY: 'auto',
            background: '#fafafa',
            padding: 12,
            fontFamily:
              'SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace',
            fontSize: 12,
            lineHeight: 1.6,
          }}
        >
          {liveLogs.length === 0 ? (
            <div style={{ color: '#999', textAlign: 'center', padding: 24 }}>
              暂无日志 — WebSocket 连接成功后实时显示
            </div>
          ) : (
            liveLogs.map((l, i) => (
              <div key={i} style={{ color: STREAM_COLOR[l.stream] || '#333' }}>
                <span style={{ color: '#bbb', marginRight: 8 }}>{formatTs(l.ts)}</span>
                <Tag
                  color={
                    l.stream === 'stderr'
                      ? 'error'
                      : l.stream === 'system'
                        ? 'blue'
                        : 'default'
                  }
                  style={{ marginRight: 8 }}
                >
                  {STREAM_LABEL[l.stream] || l.stream}
                </Tag>
                {l.node_id ? (
                  <span style={{ color: '#888', marginRight: 8 }}>[{l.node_id}]</span>
                ) : null}
                <span>{l.message}</span>
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </Card>

      <ArtifactViewer runId={id ?? ''} runStatus={overallStatus} />
    </div>
  );
}