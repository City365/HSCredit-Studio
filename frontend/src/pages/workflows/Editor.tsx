/**
 * 工作流编辑器 — react-flow 画布 + 节点库 + 节点配置 Drawer.
 *
 * @see docs/design/04-ui-design.md 4.1, 4.2, 4.3
 *
 * 关键设计：
 *   - 节点库通过 `useApiQuery` + `nodesApi.list()` 从后端加载（替换硬编码 NODE_LIBRARY）
 *   - 拖拽：通过 dataTransfer 传递 node_type，drop 时根据鼠标坐标计算 position
 *   - 节点数据：data 中携带 node_type/name/category/icon/params，状态由 execution 字段体现
 *   - 参数表单：从后端 contract.params 动态渲染（FormBuilder 已支持）
 *   - 保存：调用 workflowsApi.create/update，传入 WorkflowDefinition
 *   - 运行：调 runsApi.submit，提交后跳转 /runs/{run_id}
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  ReactFlowProvider,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
  type EdgeChange,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Layout, Button, Space, message, Drawer, Typography, Tag, Spin } from 'antd';
import { SaveOutlined, PlayCircleOutlined, FolderOpenOutlined } from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';
import { workflowsApi } from '@/api/workflows';
import { runsApi } from '@/api/runs';
import { nodesApi } from '@/api/nodes';
import { NodeCard, type NodeCardData } from '@/components/NodeCard';
import { FormBuilder } from '@/components/FormBuilder';
import { useApiQuery, useApiMutation } from '@/hooks/useApi';
import type { NodeDefinition, ParamSpec, WorkflowDefinition } from '@/types';

const { Sider, Content } = Layout;

// react-flow 自定义节点类型映射
const nodeTypes = { hscredit: NodeCard };

const CATEGORY_COLORS: Record<string, string> = {
  数据接入: 'blue',
  EDA: 'cyan',
  特征工程: 'green',
  特征筛选: 'orange',
  模型训练: 'red',
  评分卡与规则: 'purple',
  报告与部署: 'magenta',
};

function EditorInner() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const isNew = !id || id === 'new';

  const [nodes, setNodes] = useState<Node<NodeCardData, 'hscredit'>[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedNode, setSelectedNode] = useState<Node<NodeCardData, 'hscredit'> | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [workflowName] = useState('新建工作流');

  // 编辑模式：加载工作流
  const { data: workflow } = useApiQuery(['workflow', id], workflowsApi.get, id ?? '', {
    enabled: !isNew,
  });

  // 节点库：动态加载（替换原硬编码 NODE_LIBRARY）
  const {
    data: nodeDefinitions,
    isLoading: isLoadingNodes,
    error: nodeDefinitionsError,
  } = useApiQuery(
    ['node-definitions'],
    () => nodesApi.list({ enabled_only: true }),
    {},
  );

  useEffect(() => {
    if (!workflow) return;
    const def = workflow.definition;
    if (def) {
      setNodes(
        def.nodes.map((n) => ({
          id: n.id,
          type: 'hscredit',
          position: n.position,
          data: {
            node_type: (n.data?.node_type as string) ?? n.type,
            name: (n.data?.name as string) ?? n.label ?? n.type,
            category: (n.data?.category as string) ?? '',
            icon: (n.data?.icon as string) ?? '⚙️',
            params: (n.data?.params as Record<string, unknown>) ?? {},
          },
        })),
      );
      setEdges(
        def.edges.map((e) => ({
          id: e.id ?? `${e.source}-${e.target}`,
          source: e.source,
          target: e.target,
          animated: true,
          style: { stroke: '#1890ff' },
        })),
      );
    }
  }, [workflow]);

  // 按 category 分组节点库
  const groupedLibrary = useMemo(() => {
    const groups: Record<string, NodeDefinition[]> = {};
    const defs = nodeDefinitions ?? [];
    defs.forEach((n) => {
      if (!groups[n.category]) groups[n.category] = [];
      groups[n.category]!.push(n);
    });
    return groups;
  }, [nodeDefinitions]);

  // 节点类型 → 完整 contract 的查找表（O(1)）
  const contractByType = useMemo(() => {
    const map: Record<string, NodeDefinition> = {};
    (nodeDefinitions ?? []).forEach((d) => {
      map[d.node_type] = d;
    });
    return map;
  }, [nodeDefinitions]);

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => setNodes((ns) => applyNodeChanges(changes, ns) as Node<NodeCardData, 'hscredit'>[]),
    [],
  );
  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => setEdges((es) => applyEdgeChanges(changes, es)),
    [],
  );
  const onConnect = useCallback(
    (connection: Connection) =>
      setEdges((es) =>
        addEdge(
          {
            ...connection,
            animated: true,
            style: { stroke: '#1890ff' },
          },
          es,
        ),
      ),
    [],
  );

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const nodeType = event.dataTransfer.getData('application/hscredit-node-type');
      if (!nodeType) return;
      const def = contractByType[nodeType];
      if (!def) return;

      const reactFlowBounds = (event.target as HTMLElement).getBoundingClientRect();
      const position = {
        x: Math.max(0, event.clientX - reactFlowBounds.left - 90),
        y: Math.max(0, event.clientY - reactFlowBounds.top - 40),
      };

      const newNode: Node<NodeCardData, 'hscredit'> = {
        id: `${def.node_type}_${Date.now()}`,
        type: 'hscredit',
        position,
        data: {
          node_type: def.node_type,
          name: def.name,
          category: def.category,
          icon: def.icon || '⚙️',
          params: {},
        },
      };
      setNodes((ns) => [...ns, newNode]);
    },
    [contractByType],
  );

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setSelectedNode(node as Node<NodeCardData, 'hscredit'>);
      setDrawerOpen(true);
    },
    [],
  );

  const handleParamChange = (values: Record<string, unknown>): void => {
    if (!selectedNode) return;
    const sid = selectedNode.id;
    setNodes((ns) =>
      ns.map((n) =>
        n.id === sid
          ? ({ ...n, data: { ...n.data, params: values } } as Node<NodeCardData, 'hscredit'>)
          : n,
      ),
    );
    setSelectedNode((prev) =>
      prev ? (prev.data?.params !== values ? { ...prev, data: { ...prev.data, params: values } } : prev) : prev,
    );
  };

  // 保存：新建 or 更新
  const saveMutation = useApiMutation(
    async (def: WorkflowDefinition) => {
      if (isNew) {
        return await workflowsApi.create({
          name: workflowName,
          definition: def,
          tags: [],
        });
      }
      return await workflowsApi.update(id!, {
        definition: def,
        change_summary: 'Editor save',
      });
    },
    {
      onSuccess: (wf) => {
        message.success('保存成功');
        navigate(`/workflows/${wf.id}`);
      },
      onError: (err: Error) => message.error(err.message),
    },
  );

  const handleSave = (): void => {
    const def: WorkflowDefinition = {
      nodes: nodes.map((n) => ({
        id: n.id,
        type: n.data.node_type,
        position: n.position,
        label: n.data.name,
        data: {
          node_type: n.data.node_type,
          name: n.data.name,
          category: n.data.category,
          icon: n.data.icon,
          params: n.data.params ?? {},
        },
      })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        source_handle: e.sourceHandle ?? null,
        target_handle: e.targetHandle ?? null,
      })),
    };
    saveMutation.mutate(def);
  };

  // 运行
  const runMutation = useApiMutation(
    async () => {
      if (isNew) throw new Error('请先保存工作流');
      const run = await runsApi.submit(id!);
      message.success(`Run 已提交: #${run.run_number}`);
      navigate(`/runs/${run.id}`);
    },
    {
      onError: (err: Error) => message.warning(err.message),
    },
  );

  // 抽屉中的节点参数规格：直接从后端 contract.params 取（替换硬编码空数组）
  const selectedParams: ParamSpec[] = useMemo(() => {
    if (!selectedNode) return [];
    const def = contractByType[selectedNode.data.node_type];
    return (def?.contract?.params as ParamSpec[] | undefined) ?? [];
  }, [selectedNode, contractByType]);

  const selectedParamValues: Record<string, unknown> = useMemo(() => {
    if (!selectedNode) return {};
    return selectedNode.data.params ?? {};
  }, [selectedNode]);

  return (
    <Layout style={{ height: 'calc(100vh - 130px)' }}>
      <Sider
        width={220}
        theme="light"
        style={{ overflow: 'auto', borderRight: '1px solid #f0f0f0', background: '#fafafa' }}
      >
        <Typography.Title level={5} style={{ padding: '12px 16px 4px', margin: 0 }}>
          节点库
        </Typography.Title>
        {isLoadingNodes && (
          <div style={{ padding: '16px', textAlign: 'center' }}>
            <Spin size="small" /> <span style={{ marginLeft: 8, color: '#999' }}>加载中…</span>
          </div>
        )}
        {nodeDefinitionsError && (
          <div style={{ padding: '16px', color: '#ff4d4f', fontSize: 12 }}>
            节点库加载失败：{nodeDefinitionsError.message}
          </div>
        )}
        {Object.entries(groupedLibrary).map(([category, defs]) => (
          <div key={category} style={{ marginBottom: 12 }}>
            <div style={{ padding: '4px 16px', color: '#999', fontSize: 12 }}>
              <Tag color={CATEGORY_COLORS[category] ?? 'default'} style={{ marginRight: 4 }}>
                {category}
              </Tag>
              <span style={{ marginLeft: 4 }}>{defs.length}</span>
            </div>
            {defs.map((def) => (
              <div
                key={def.node_type}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData('application/hscredit-node-type', def.node_type);
                  e.dataTransfer.effectAllowed = 'move';
                }}
                style={{
                  padding: '8px 16px',
                  cursor: 'grab',
                  background: '#fff',
                  margin: '2px 8px',
                  borderRadius: 4,
                  border: '1px solid #f0f0f0',
                }}
              >
                <span style={{ marginRight: 8 }}>{def.icon || '⚙️'}</span>
                {def.name}
              </div>
            ))}
          </div>
        ))}
      </Sider>
      <Content style={{ position: 'relative', background: '#fff' }}>
        <div style={{ position: 'absolute', top: 8, right: 8, zIndex: 10 }}>
          <Space>
            <Button icon={<FolderOpenOutlined />} onClick={() => navigate('/workflows')}>
              返回列表
            </Button>
            <Button
              icon={<SaveOutlined />}
              onClick={handleSave}
              loading={saveMutation.isPending}
            >
              保存
            </Button>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={() => runMutation.mutate()}
              loading={runMutation.isPending}
            >
              运行
            </Button>
          </Space>
        </div>
        <div
          style={{ width: '100%', height: '100%' }}
          onDragOver={(e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
          }}
          onDrop={onDrop}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            nodeTypes={nodeTypes}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={16} />
            <Controls />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </div>
      </Content>
      <Drawer
        title={selectedNode?.data?.name ?? '节点配置'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={400}
        destroyOnClose
      >
        {selectedNode && (
          <FormBuilder
            params={selectedParams}
            values={selectedParamValues}
            onChange={handleParamChange}
          />
        )}
      </Drawer>
    </Layout>
  );
}

export default function WorkflowEditorPage() {
  return (
    <ReactFlowProvider>
      <EditorInner />
    </ReactFlowProvider>
  );
}
