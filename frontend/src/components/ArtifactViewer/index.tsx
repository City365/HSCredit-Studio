/**
 * 产物查看器（ArtifactViewer）— 列出 Run 所有节点产物并提供下载.
 *
 * 数据来源：`runsApi.listArtifacts(runId)` → 后端 `GET /runs/{id}/artifacts`.
 * 每个产物已携带预签名下载 URL（默认 1 小时有效）.
 *
 * 设计要点：
 *   - 按节点（node_id / node_name）分组展示，便于定位产物来源
 *   - 类型列显示中文标签 + 颜色 tag
 *   - 大小自动换算 KB/MB/GB
 *   - 下载列：download_url 存在时按钮可点击；否则显示「暂不可用」
 *   - sha256 前 12 位 + 复制按钮（防误读）
 */

import { useMemo, useState } from 'react';
import { Card, Table, Tag, Button, Tooltip, Empty, Space, Typography, message } from 'antd';
import {
  FileOutlined,
  DownloadOutlined,
  CopyOutlined,
  FolderOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useApiQuery } from '@/hooks/useApi';
import { runsApi } from '@/api/runs';
import type { Artifact } from '@/types';

const { Text } = Typography;

/** 产物类型 → 中文标签 + 颜色. */
const TYPE_META: Record<string, { label: string; color: string; icon: string }> = {
  parquet: { label: 'Parquet 数据', color: 'blue', icon: '📊' },
  excel: { label: 'Excel 文件', color: 'green', icon: '📗' },
  pmml: { label: 'PMML 模型', color: 'purple', icon: '🧬' },
  json: { label: 'JSON 数据', color: 'orange', icon: '📋' },
  png: { label: 'PNG 图像', color: 'magenta', icon: '🖼️' },
  pdf: { label: 'PDF 文档', color: 'red', icon: '📕' },
  log: { label: '日志文件', color: 'default', icon: '📜' },
  pickle: { label: 'Pickle 对象', color: 'gold', icon: '🧪' },
  model: { label: '模型对象', color: 'gold', icon: '🧪' },
  binner: { label: '分箱器', color: 'cyan', icon: '📐' },
  scorecard: { label: '评分卡', color: 'purple', icon: '💳' },
};

function formatSize(bytes: number): string {
  if (!bytes || bytes < 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function typeMeta(t: string): { label: string; color: string; icon: string } {
  return TYPE_META[t] ?? { label: t, color: 'default', icon: '📦' };
}

export interface ArtifactViewerProps {
  runId: string;
  /** Run 状态 — 仅 success/cached 时展示，避免误导用户下载不完整产物.*/
  runStatus?: string;
  /** 卡片标题. */
  title?: string;
}

export function ArtifactViewer({
  runId,
  runStatus,
  title = '运行产物',
}: ArtifactViewerProps) {
  const { data, isLoading, error } = useApiQuery(
    ['run-artifacts', runId],
    runsApi.listArtifacts,
    runId,
  );

  const grouped = useMemo(() => {
    const map = new Map<string, { nodeId: string; nodeType: string; nodeName: string; items: Artifact[] }>();
    (data ?? []).forEach((a) => {
      const key = `${a.node_type ?? 'unknown'}::${a.node_id ?? a.id}`;
      if (!map.has(key)) {
        map.set(key, {
          nodeId: a.node_id ?? '',
          nodeType: a.node_type ?? 'unknown',
          nodeName: a.node_name ?? a.node_type ?? '未知节点',
          items: [],
        });
      }
      map.get(key)!.items.push(a);
    });
    return Array.from(map.values());
  }, [data]);

  if (runStatus && !['success', 'cached', 'cached_hit', 'partial'].includes(runStatus)) {
    return (
      <Card title={<Space><FileOutlined /><span>{title}</span></Space>} size="small">
        <Empty
          description={`Run 状态为「${runStatus}」，产物将在执行成功后展示`}
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card title={<Space><FileOutlined /><span>{title}</span></Space>} size="small" loading>
        <div style={{ minHeight: 60 }} />
      </Card>
    );
  }

  if (error) {
    return (
      <Card title={<Space><FileOutlined /><span>{title}</span></Space>} size="small">
        <Text type="danger">产物加载失败：{error.message}</Text>
      </Card>
    );
  }

  if (!data || data.length === 0) {
    return (
      <Card title={<Space><FileOutlined /><span>{title}</span></Space>} size="small">
        <Empty description="该 Run 暂无产物" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    );
  }

  return (
    <Card
      title={
        <Space>
          <FileOutlined />
          <span>{title}</span>
          <Tag color="blue">{data.length} 个</Tag>
        </Space>
      }
      size="small"
    >
      {grouped.map((g) => {
        const columns: ColumnsType<Artifact> = [
          {
            title: '类型',
            dataIndex: 'artifact_type',
            key: 'artifact_type',
            width: 140,
            render: (t: string) => {
              const meta = typeMeta(t);
              return (
                <Tag color={meta.color}>
                  <span style={{ marginRight: 4 }}>{meta.icon}</span>
                  {meta.label}
                </Tag>
              );
            },
          },
          {
            title: '输出端口',
            dataIndex: 'output_name',
            key: 'output_name',
            width: 140,
            render: (v: string | null | undefined) =>
              v ? <Text code>{v}</Text> : <Text type="secondary">—</Text>,
          },
          {
            title: '大小',
            dataIndex: 'size_bytes',
            key: 'size_bytes',
            width: 100,
            render: (b: number) => <Text>{formatSize(b)}</Text>,
          },
          {
            title: 'SHA-256',
            dataIndex: 'sha256',
            key: 'sha256',
            width: 200,
            render: (s: string) => (
              <Tooltip title={s}>
                <Space size={4}>
                  <Text code style={{ fontSize: 12 }}>{s.slice(0, 12)}…</Text>
                  <Button
                    size="small"
                    type="text"
                    icon={<CopyOutlined />}
                    onClick={() => {
                      navigator.clipboard?.writeText(s).then(
                        () => message.success('SHA-256 已复制'),
                        () => message.error('复制失败'),
                      );
                    }}
                  />
                </Space>
              </Tooltip>
            ),
          },
          {
            title: '存储路径',
            dataIndex: 'storage_path',
            key: 'storage_path',
            ellipsis: true,
            render: (p: string) => (
              <Tooltip title={p}>
                <Text type="secondary" style={{ fontSize: 12 }}>{p}</Text>
              </Tooltip>
            ),
          },
          {
            title: '操作',
            key: 'action',
            width: 110,
            render: (_: unknown, record: Artifact) =>
              record.download_url ? (
                <Button
                  type="primary"
                  size="small"
                  icon={<DownloadOutlined />}
                  href={record.download_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  下载
                </Button>
              ) : (
                <Text type="secondary" style={{ fontSize: 12 }}>暂不可用</Text>
              ),
          },
        ];

        return (
          <div key={`${g.nodeType}-${g.nodeId}`} style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 8 }}>
              <Space>
                <FolderOutlined />
                <Text strong>{g.nodeName}</Text>
                <Tag>{g.nodeType}</Tag>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {g.items.length} 个产物
                </Text>
              </Space>
            </div>
            <Table<Artifact>
              rowKey="id"
              size="small"
              dataSource={g.items}
              columns={columns}
              pagination={false}
              bordered
            />
          </div>
        );
      })}
    </Card>
  );
}

export default ArtifactViewer;

// 显式导出供 useState 用（避免 lint 警告）
export { useState };
