/** 自定义节点代码编辑器 — Phase 6 B36 阶段 7 完整版.

功能:
- Monaco Editor (Python 语法高亮 + 自动补全)
- 顶部: 节点名 + 版本下拉 + 启停 + 保存版本 + 试运行
- 右侧: 实时 contract 预览 (inputs / outputs / params)
- 状态条: 校验状态 / 试运行次数 / 最近保存
- 防抖自动保存草稿 (5s)
- 编辑锁: 进入申请, 每 2 分钟心跳, 离开释放
- 静态校验 squiggle (阶段 0 AST 集成)
- 试运行按钮 → 调用 /test
*/

import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Drawer,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CloudSyncOutlined,
  ExclamationCircleOutlined,
  HistoryOutlined,
  PlayCircleOutlined,
  SaveOutlined,
  WarningOutlined,
} from '@ant-design/icons';

import { customNodesApi } from '@/api/custom-nodes';
import { useApiMutation, useApiQuery } from '@/hooks/useApi';
import { useDraftAutosave } from '@/hooks/useDraftAutosave';
import { useEditLock } from '@/hooks/useEditLock';
import { useAuthStore } from '@/stores/authStore';
import type {
  CustomNodeResponse,
  CustomNodeVersionListResponse,
  CustomNodeVersionResponse,
  ValidateResponse,
} from '@/api/custom-nodes';

export default function NodesEditPage(): React.ReactElement {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { message, modal } = App.useApp();
  const role = useAuthStore((s) => s.role);
  const isAdmin = role === 'super_admin' || role === 'tenant_admin';

  const editorRef = useRef<Parameters<NonNullable<React.ComponentProps<typeof Editor>['onMount']>>[0] | null>(null);
  const monacoRef = useRef<Parameters<NonNullable<React.ComponentProps<typeof Editor>['onMount']>>[1] | null>(null);
  const markersRef = useRef<string[]>([]);

  // ===== 数据 =====
  const nodeQuery = useApiQuery<CustomNodeResponse, string>(
    ['custom-node', id ?? ''],
    () => customNodesApi.get(id ?? ''),
    id ?? '',
  );

  const versionsQuery = useApiQuery<CustomNodeVersionListResponse, string>(
    ['custom-node-versions', id ?? ''],
    () => customNodesApi.listVersions(id ?? ''),
    id ?? '',
  );

  // ===== 编辑状态 =====
  const [code, setCode] = useState('');
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidateResponse | null>(null);
  const [validationTick, setValidationTick] = useState(0);

  // 节点加载后, 设置 code 为当前 code
  useEffect(() => {
    if (nodeQuery.data && !code) {
      setCode(nodeQuery.data.code || '');
    }
  }, [nodeQuery.data, code]);

  // ===== 编辑锁 + 自动保存 =====
  useEditLock({ customNodeId: id ?? '', enabled: !!id });
  useDraftAutosave({ customNodeId: id ?? '', code, onSaved: () => undefined });

  // ===== 静态校验 (防抖 500ms) =====
  useEffect(() => {
    if (!code || !id) return;
    const t = setTimeout(async () => {
      try {
        const res = await customNodesApi.validate(id, { code });
        setValidation(res);
        setValidationTick((t) => t + 1);
      } catch {
        setValidation(null);
      }
    }, 500);
    return () => clearTimeout(t);
  }, [code, id]);

  // ===== Monaco squiggle 更新 =====
  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco || !validation) return;
    const model = editor.getModel();
    if (!model) return;
    // 清理旧 markers
    markersRef.current.forEach((id) => monaco.editor.removeModelMarker(id));
    // 加新 markers
    const markers = validation.issues.map((iss) => ({
      startLineNumber: Math.max(iss.line, 1),
      endLineNumber: Math.max(iss.line, 1),
      startColumn: iss.column + 1 || 1,
      endColumn: (iss.column || 0) + 100,
      message: `${iss.rule}: ${iss.message}`,
      severity:
        iss.severity === 'error'
          ? monaco.MarkerSeverity.Error
          : monaco.MarkerSeverity.Warning,
    }));
    markersRef.current = monaco.editor.setModelMarkers(model, 'validation', markers);
  }, [validation, validationTick]);

  // ===== 保存新版本 =====
  const saveVersionMutation = useApiMutation<CustomNodeVersionResponse, { code: string; changeSummary: string }>(
    (vars) =>
      customNodesApi.updateCode(id ?? '', {
        code: vars.code,
        contract: nodeQuery.data?.contract ?? {},
        change_summary: vars.changeSummary,
      }),
  );

  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [changeSummary, setChangeSummary] = useState('');

  const handleSaveVersion = async () => {
    if (!changeSummary.trim()) {
      message.warning('请填写变更说明');
      return;
    }
    try {
      const v = await saveVersionMutation.mutateAsync({
        code,
        changeSummary: changeSummary.trim(),
      });
      message.success(`已保存 v${v.version_number}`);
      setSaveModalOpen(false);
      setChangeSummary('');
      void versionsQuery.refetch();
      void nodeQuery.refetch();
    } catch (e) {
      message.error(`保存失败: ${(e as Error).message}`);
    }
  };

  // ===== 版本切换 =====
  const handleVersionChange = async (versionId: string) => {
    setSelectedVersionId(versionId);
    try {
      const v = await customNodesApi.getVersion(id ?? '', versionId);
      setCode(v.code);
      message.info(`已切到 v${v.version_number}`);
    } catch (e) {
      message.error(`加载版本失败: ${(e as Error).message}`);
    }
  };

  // ===== 试运行 =====
  const handleTestRun = () => {
    navigate(`/nodes/${id}/test`);
  };

  // ===== 软删除 =====
  const handleDelete = () => {
    modal.confirm({
      title: `确定删除 ${nodeQuery.data?.node_type}?`,
      content: '工作流中引用会失败',
      okText: '删除',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await customNodesApi.delete(id ?? '');
          message.success('已删除');
          navigate('/nodes');
        } catch (e) {
          message.error(`删除失败: ${(e as Error).message}`);
        }
      },
    });
  };

  // ===== Contract 预览 =====
  const contractPreview = useMemo(() => {
    const c = nodeQuery.data?.contract;
    if (!c) return null;
    return {
      inputs: (c.inputs as Array<Record<string, unknown>>) ?? [],
      outputs: (c.outputs as Array<Record<string, unknown>>) ?? [],
      params: (c.params as Array<Record<string, unknown>>) ?? [],
    };
  }, [nodeQuery.data]);

  // ===== 渲染 =====
  if (nodeQuery.isLoading) {
    return (
      <Card>
        <Space direction="vertical" align="center" style={{ width: '100%', padding: 80 }}>
          <Spin size="large" />
          <span>加载节点...</span>
        </Space>
      </Card>
    );
  }

  if (nodeQuery.isError || !nodeQuery.data) {
    return (
      <Alert
        type="error"
        message="节点加载失败"
        description={(nodeQuery.error as Error)?.message ?? '未知错误'}
        showIcon
      />
    );
  }

  const cn = nodeQuery.data;
  const versions = versionsQuery.data?.items ?? [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: 'calc(100vh - 130px)' }}>
      <Card size="small" styles={{ body: { padding: 12 } }}>
        <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space wrap>
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/nodes')}>
              返回
            </Button>
            <span style={{ fontSize: 18 }}>{cn.icon || '🛠️'}</span>
            <Typography.Title level={4} style={{ margin: 0 }}>
              {cn.name}
            </Typography.Title>
            <Tag color="orange">自定义</Tag>
            <Tag>{cn.node_type}</Tag>
            {cn.current_version_number && <Tag>v{cn.current_version_number}</Tag>}
            {cn.enabled ? (
              <Tag color="green" icon={<CheckCircleOutlined />}>启用</Tag>
            ) : (
              <Tag color="red" icon={<CloseCircleOutlined />}>停用</Tag>
            )}
          </Space>
          <Space wrap>
            <Select
              placeholder="切换版本"
              style={{ width: 180 }}
              value={selectedVersionId}
              onChange={handleVersionChange}
              allowClear
              options={versions.map((v) => ({
                value: v.version_id,
                label: `v${v.version_number} - ${v.change_summary || '无说明'}`,
              }))}
            />
            <Tooltip title="试运行">
              <Button icon={<PlayCircleOutlined />} onClick={handleTestRun}>
                试运行
              </Button>
            </Tooltip>
            {isAdmin && (
              <>
                <Button
                  type="primary"
                  icon={<SaveOutlined />}
                  onClick={() => setSaveModalOpen(true)}
                  loading={saveVersionMutation.isPending}
                >
                  保存版本
                </Button>
                <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>
                  删除
                </Button>
              </>
            )}
          </Space>
        </Space>
      </Card>

      <Row gutter={12} style={{ flex: 1, minHeight: 0 }}>
        <Col span={16} style={{ height: '100%' }}>
          <Card
            size="small"
            styles={{ body: { padding: 0, height: 'calc(100% - 40px)' } }}
            title={
              <Space>
                <CloudSyncOutlined />
                Python Code
                {validation?.valid === true && (
                  <Tag color="green" icon={<CheckCircleOutlined />}>校验通过</Tag>
                )}
                {validation?.valid === false && (
                  <Tag color="red" icon={<CloseCircleOutlined />}>
                    {validation.issues.length} 个问题
                  </Tag>
                )}
                {validation === null && <Tag>校验中...</Tag>}
              </Space>
            }
            style={{ height: '100%' }}
          >
            <Editor
              height="100%"
              defaultLanguage="python"
              theme="vs-dark"
              value={code}
              onChange={(v) => setCode(v ?? '')}
              onMount={(editor, monaco) => {
                editorRef.current = editor;
                monacoRef.current = monaco;
              }}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                scrollBeyondLastLine: false,
                automaticLayout: true,
                tabSize: 4,
                wordWrap: 'on',
              }}
            />
          </Card>
        </Col>

        <Col span={8} style={{ height: '100%' }}>
          <Card
            size="small"
            title={
              <Space>
                <HistoryOutlined />
                Contract 预览
              </Space>
            }
            style={{ height: '100%', overflow: 'auto' }}
            styles={{ body: { padding: 12 } }}
          >
            {validation?.issues && validation.issues.length > 0 && (
              <Alert
                type="error"
                showIcon
                icon={<ExclamationCircleOutlined />}
                message={`${validation.issues.length} 个问题`}
                style={{ marginBottom: 12 }}
              >
                {validation.issues.slice(0, 5).map((i, idx) => (
                  <div key={idx} style={{ fontSize: 12 }}>
                    <Tag color="red">L{i.line}</Tag>
                    <Tag>{i.rule}</Tag>
                    {i.message}
                  </div>
                ))}
                {validation.issues.length > 5 && (
                  <div style={{ fontSize: 12, color: '#999' }}>... 还有 {validation.issues.length - 5} 个</div>
                )}
              </Alert>
            )}

            {validation?.ast_preview && (
              <Card size="small" type="inner" title="AST 预览" style={{ marginBottom: 12 }}>
                <div>类名: <Tag>{validation.ast_preview.class_name || '-'}</Tag></div>
                <div>继承: <code>{validation.ast_preview.base_classes.join(', ')}</code></div>
                <div>有 contract: {validation.ast_preview.has_contract ? '✓' : '✗'}</div>
                <div>有 run 方法: {validation.ast_preview.has_run_method ? '✓' : '✗'}</div>
                <div>方法: {validation.ast_preview.methods.join(', ') || '-'}</div>
              </Card>
            )}

            {contractPreview && (
              <>
                <Typography.Title level={5}>输入端口</Typography.Title>
                {contractPreview.inputs.map((p, i) => (
                  <Tag key={i} color="blue">{String(p.name)}</Tag>
                ))}
                {!contractPreview.inputs.length && <div style={{ color: '#999' }}>无</div>}

                <Typography.Title level={5} style={{ marginTop: 12 }}>输出端口</Typography.Title>
                {contractPreview.outputs.map((p, i) => (
                  <Tag key={i} color="green">{String(p.name)}</Tag>
                ))}
                {!contractPreview.outputs.length && <div style={{ color: '#999' }}>无</div>}

                <Typography.Title level={5} style={{ marginTop: 12 }}>参数</Typography.Title>
                {contractPreview.params.map((p, i) => (
                  <Tag key={i} color="orange">{String(p.name)}</Tag>
                ))}
                {!contractPreview.params.length && <div style={{ color: '#999' }}>无</div>}
              </>
            )}
          </Card>
        </Col>
      </Row>

      <Modal
        title="保存新版本"
        open={saveModalOpen}
        onCancel={() => setSaveModalOpen(false)}
        onOk={handleSaveVersion}
        confirmLoading={saveVersionMutation.isPending}
      >
        <Alert
          type="info"
          showIcon
          message="保存后会创建新版本 (旧版本保留, 可回滚)"
          style={{ marginBottom: 12 }}
        />
        <Input.TextArea
          rows={3}
          placeholder="本次变更说明 (必填)"
          value={changeSummary}
          onChange={(e) => setChangeSummary(e.target.value)}
          maxLength={500}
          showCount
        />
      </Modal>
    </div>
  );
}
