/**
 * react-flow 自定义节点卡片.
 *
 * 视觉规范参考 docs/design/04-ui-design.md 4.2
 *  - 左侧 4px 色条表示节点分类
 *  - 顶部 icon + 名称
 *  - 底部分类 Tag + 实时状态圆点
 *  - 状态颜色见 STATUS_COLOR
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { Tag, Tooltip } from 'antd';
import styles from './NodeCard.module.css';

const CATEGORY_COLOR: Record<string, string> = {
  数据接入: '#1890ff',
  EDA: '#13c2c2',
  特征工程: '#52c41a',
  特征筛选: '#faad14',
  模型训练: '#f5222d',
  评分卡与规则: '#722ed1',
  报告与部署: '#eb2f96',
};

/**
 * 状态颜色映射（包含 RunStatus 与 NodeExecutionStatus 全部取值，
 * 未匹配值降级到 unknown 灰色）.
 */
const STATUS_COLOR: Record<string, string> = {
  pending: '#d9d9d9',
  queued: '#d9d9d9',
  running: '#1890ff',
  cached: '#722ed1',
  success: '#52c41a',
  failed: '#f5222d',
  cancelled: '#8c8c8c',
  retrying: '#faad14',
  skipped: '#d9d9d9',
  unknown: '#d9d9d9',
};

/** 查询状态颜色，未命中返回 unknown 灰色. */
function colorFor(status: string | undefined): string {
  if (!status) return STATUS_COLOR['unknown']!;
  return STATUS_COLOR[status] ?? STATUS_COLOR['unknown']!;
}

export interface NodeCardData extends Record<string, unknown> {
  node_type: string;
  name: string;
  category: string;
  icon: string;
  execution?: {
    status: string;
    progress?: number;
  };
  params?: Record<string, unknown>;
}

export type NodeCardNode = Node<NodeCardData, 'hscredit'>;

function NodeCardInner({ data, selected }: NodeProps<NodeCardNode>) {
  const categoryColor = CATEGORY_COLOR[data.category] ?? '#1890ff';
  const status = data.execution?.status;
  return (
    <div
      className={`${styles.nodeCard} ${selected ? styles.selected : ''}`}
      style={{ borderLeftColor: categoryColor }}
    >
      <Handle type="target" position={Position.Left} className={styles.handle} />
      <div className={styles.header}>
        <span className={styles.icon} aria-hidden>
          {data.icon}
        </span>
        <span className={styles.name}>{data.name}</span>
      </div>
      <div className={styles.meta}>
        <Tag color={categoryColor}>{data.category}</Tag>
        {status && (
          <Tooltip title={`状态: ${status}`}>
            <span
              className={styles.statusDot}
              style={{ background: colorFor(status) }}
              aria-label={`status-${status}`}
            />
          </Tooltip>
        )}
      </div>
      <Handle type="source" position={Position.Right} className={styles.handle} />
    </div>
  );
}

export const NodeCard = memo(NodeCardInner);
