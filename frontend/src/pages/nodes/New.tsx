/** 新增自定义节点向导 — Phase 6 B36 阶段 8.

5 步流程:
1. 起点选择 (空白 / 复制系统节点)
2. 基础信息 (node_type, name, category, icon, visibility)
3. 代码编辑 (Monaco + 模板)
4. 测试样本 + 试运行
5. 确认 + 保存
*/

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Steps,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CodeOutlined,
  ExperimentOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';

import { customNodesApi, nodesApi } from '@/api';
import { useApiMutation, useApiQuery } from '@/hooks/useApi';
import type {
  CustomNodeCreateRequest,
  CustomNodeResponse,
  NodeDefinition,
  TestRunResponse,
} from '@/api';

type StartMode = 'blank' | 'copy-system';

interface CopyTarget {
  node_type: string;
  name: string;
  category: string;
  icon: string;
  code: string;
}

const TEMPLATE_BASE_NODE = `# 节点类必须继承 BaseNode 并定义 contract
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.schemas.node_contract import NodeContract, PortSchema, ParamSpec

class MyNode(BaseNode):
    contract = NodeContract(
        node_type='my_node',
        category='特征工程',
        name='我的节点',
        inputs=[
            PortSchema(name='df', type='DataFrame', required=True),
        ],
        outputs=[
            PortSchema(name='result', type='DataFrame'),
        ],
        params=[
            ParamSpec(name='threshold', type='float', default=0.5),
        ],
    )

    def run(self, inputs, params):
        df = inputs['df']
        threshold = params.get('threshold', 0.5)
        return {'result': df.head()}
`;

export default function NodesNewPage(): React.ReactElement {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [currentStep, setCurrentStep] = useState(0);

  // Step 1: 起点
  const [startMode, setStartMode] = useState<StartMode>('blank');
  const [copyTarget, setCopyTarget] = useState<CopyTarget | null>(null);

  // Step 2: 基础信息
  const [form] = Form.useForm<{
    node_type: string;
    name: string;
    category: string;
    icon: string;
    visibility: 'private' | 'tenant' | 'public';
  }>();
  const [baseInfo, setBaseInfo] = useState<{
    node_type: string;
    name: string;
    category: string;
    icon: string;
    visibility: 'private' | 'tenant' | 'public';
  } | null>(null);

  // Step 3: 代码
  const [code, setCode] = useState(TEMPLATE_BASE_NODE);

  // Step 4: 试运行
  const [testResult, setTestResult] = useState<TestRunResponse | null>(null);

  // Step 5: 确认
  const [contract, setContract] = useState<Record<string, unknown>>({});

  // 系统节点列表 (用于"复制")
  const sysNodesQuery = useApiQuery<NodeDefinition[], { enabled_only: boolean }>(
    ['nodes', 'list-all'],
    () => nodesApi.list({ enabled_only: false, include_contract: false }),
    { enabled_only: false },
  );

  const createMutation = useApiMutation<CustomNodeResponse, CustomNodeCreateRequest>(
    (payload) => customNodesApi.create(payload),
  );

  const testMutation = useApiMutation<TestRunResponse, { code: string }>(
    async (vars) => {
      // 创建临时草稿 + 试运行? 简化: 用 detectContract 推断 contract 然后试运行
      // 实际是 /test 端点需要 custom_node_id — 所以先创建再试运行
      throw new Error('试运行需要先创建节点 (step 5 后再测)');
    },
  );

  // ===== Step 1 → 2: 起点选择后 =====
  const handleStep1Next = () => {
    if (startMode === 'copy-system' && copyTarget) {
      setCode(copyTarget.code || '');
    } else if (startMode === 'blank') {
      setCode(TEMPLATE_BASE_NODE);
    }
    setCurrentStep(1);
  };

  // ===== Step 2 → 3 =====
  const handleStep2Next = async () => {
    try {
      const values = await form.validateFields();
      setBaseInfo(values);
      setCurrentStep(2);
    } catch {
      message.warning('请填写必填字段');
    }
  };

  // ===== Step 3 → 4: AST 校验 + contract 反推 =====
  const handleStep3Next = async () => {
    // 直接构造 contract (基于模板的 BaseNode 子类) — 用户可在 UI 编辑
    // 简化: 从模板默认 contract 开始
    const defaultContract = {
      node_type: baseInfo?.node_type ?? '',
      category: baseInfo?.category ?? '',
      name: baseInfo?.name ?? '',
      inputs: [{ name: 'df', type: 'DataFrame', required: true }],
      outputs: [{ name: 'result', type: 'DataFrame' }],
      params: [{ name: 'threshold', type: 'float', default: 0.5 }],
    };
    setContract(defaultContract);
    setCurrentStep(3);
  };

  // ===== Step 5: 保存 =====
  const handleSave = async () => {
    if (!baseInfo) return;
    try {
      const payload: CustomNodeCreateRequest = {
        node_type: baseInfo.node_type,
        name: baseInfo.name,
        category: baseInfo.category,
        icon: baseInfo.icon,
        visibility: baseInfo.visibility,
        code,
        contract,
      };
      const cn = await createMutation.mutateAsync(payload);
      message.success(`已创建 ${cn.node_type}`);
      navigate(`/nodes/${cn.custom_node_id}/edit`);
    } catch (e) {
      message.error(`创建失败: ${(e as Error).message}`);
    }
  };

  const handleSelectCopyTarget = (nt: string) => {
    const target = sysNodesQuery.data?.find((n) => n.node_type === nt);
    if (target) {
      // 从 n.contract 提取 inputs/outputs/params, 生成模板代码
      const c = (target.contract as Record<string, unknown>) ?? {};
      const inputs = (c.inputs as Array<Record<string, string>>) ?? [];
      const outputs = (c.outputs as Array<Record<string, string>>) ?? [];
      const params = (c.params as Array<Record<string, unknown>>) ?? [];
      const codeTemplate = `# 复制自 ${nt}
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.schemas.node_contract import NodeContract, PortSchema, ParamSpec

class MyNode(BaseNode):
    contract = NodeContract(
        node_type='${baseInfo?.node_type ?? nt}',
        category='${(c.category as string) ?? '特征工程'}',
        name='${baseInfo?.name ?? nt} (copy)',
        inputs=[${inputs.map((p) => `PortSchema(name='${p.name}', type='${p.type}', required=${p.required ?? true})`).join(', ')}],
        outputs=[${outputs.map((p) => `PortSchema(name='${p.name}', type='${p.type}')`).join(', ')}],
        params=[${params.map((p) => `ParamSpec(name='${p.name}', type='${p.type}', default=${JSON.stringify(p.default)})`).join(', ')}],
    )

    def run(self, inputs, params):
        # TODO: 实现节点逻辑
        return {${outputs.map((p) => `'${p.name}': None`).join(', ')}}`;
      setCopyTarget({
        node_type: nt,
        name: target.name,
        category: (c.category as string) ?? '特征工程',
        icon: target.icon ?? '📦',
        code: codeTemplate,
      });
    }
  };

  return (
    <Card
      title={
        <Space>
          <Button
            icon={<ArrowLeftOutlined />}
            type="text"
            onClick={() => navigate('/nodes')}
          >
            返回
          </Button>
          <CodeOutlined /> 新增自定义节点
        </Space>
      }
    >
      <Steps
        current={currentStep}
        items={[
          { title: '起点选择' },
          { title: '基础信息' },
          { title: '代码编辑' },
          { title: '试运行' },
          { title: '确认保存' },
        ]}
        style={{ marginBottom: 24 }}
      />

      {/* Step 1: 起点选择 */}
      {currentStep === 0 && (
        <Card type="inner" title="选择起点">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Select
              value={startMode}
              onChange={setStartMode}
              style={{ width: 240 }}
              options={[
                { value: 'blank', label: '🆕 从空白创建' },
                { value: 'copy-system', label: '📋 从系统节点复制' },
              ]}
            />
            {startMode === 'copy-system' && (
              <Select
                placeholder="选择要复制的系统节点"
                style={{ width: 360 }}
                value={copyTarget?.node_type}
                onChange={handleSelectCopyTarget}
                loading={sysNodesQuery.isLoading}
                options={(sysNodesQuery.data ?? []).map((n) => ({
                  value: n.node_type,
                  label: `${n.icon} ${n.name} (${n.node_type})`,
                }))}
              />
            )}
            <div>
              <Button type="primary" onClick={handleStep1Next} disabled={startMode === 'copy-system' && !copyTarget}>
                下一步 →
              </Button>
            </div>
          </Space>
        </Card>
      )}

      {/* Step 2: 基础信息 */}
      {currentStep === 1 && (
        <Card type="inner" title="基础信息">
          <Form
            form={form}
            layout="vertical"
            initialValues={{
              node_type: 'my_node',
              name: '',
              category: '特征工程',
              icon: '🛠️',
              visibility: 'private',
            }}
          >
            <Form.Item name="node_type" label="节点类型 (node_type)" rules={[{ required: true, pattern: /^[a-z][a-z0-9_]*$/, message: '小写字母/数字/下划线, 字母开头' }]}>
              <Input placeholder="my_node" maxLength={128} />
            </Form.Item>
            <Form.Item name="name" label="名称" rules={[{ required: true, min: 1, max: 128 }]}>
              <Input placeholder="我的节点" maxLength={128} />
            </Form.Item>
            <Form.Item name="category" label="分类">
              <Select
                options={[
                  { value: '数据接入', label: '数据接入' },
                  { value: 'EDA', label: 'EDA' },
                  { value: '特征工程', label: '特征工程' },
                  { value: '特征筛选', label: '特征筛选' },
                  { value: '模型训练', label: '模型训练' },
                  { value: '评分卡与规则', label: '评分卡与规则' },
                  { value: '报告与部署', label: '报告与部署' },
                ]}
              />
            </Form.Item>
            <Form.Item name="icon" label="图标 (emoji)">
              <Input maxLength={32} />
            </Form.Item>
            <Form.Item name="visibility" label="可见性">
              <Select
                options={[
                  { value: 'private', label: '私有 (仅本人)' },
                  { value: 'tenant', label: '租户 (同租户成员)' },
                  { value: 'public', label: '公开 (需审批)' },
                ]}
              />
            </Form.Item>
            <Space>
              <Button onClick={() => setCurrentStep(0)}>← 上一步</Button>
              <Button type="primary" onClick={handleStep2Next}>
                下一步 →
              </Button>
            </Space>
          </Form>
        </Card>
      )}

      {/* Step 3: 代码编辑 */}
      {currentStep === 2 && (
        <Card
          type="inner"
          title={
            <Space>
              <CodeOutlined />
              代码编辑 (Python, 继承 BaseNode)
              {baseInfo && <Tag color="blue">{baseInfo.node_type}</Tag>}
            </Space>
          }
        >
          <Alert
            type="info"
            showIcon
            message="模板代码已预填 BaseNode 子类结构, 修改 contract 和 run() 方法即可"
            style={{ marginBottom: 12 }}
          />
          <div style={{ height: 360, border: '1px solid #d9d9d9', borderRadius: 4 }}>
            <Editor
              height="100%"
              defaultLanguage="python"
              theme="vs-dark"
              value={code}
              onChange={(v) => setCode(v ?? '')}
              options={{
                minimap: { enabled: false },
                fontSize: 12,
                scrollBeyondLastLine: false,
                automaticLayout: true,
              }}
            />
          </div>
          <Space style={{ marginTop: 12 }}>
            <Button onClick={() => setCurrentStep(1)}>← 上一步</Button>
            <Button type="primary" onClick={handleStep3Next}>
              下一步 →
            </Button>
          </Space>
        </Card>
      )}

      {/* Step 4: 试运行 */}
      {currentStep === 3 && (
        <Card
          type="inner"
          title={
            <Space>
              <ExperimentOutlined />
              试运行 (暂存为后续)
            </Space>
          }
        >
          <Alert
            type="info"
            showIcon
            message="试运行需要节点已存在. 这里先跳过, 创建后可到编辑页试运行."
            style={{ marginBottom: 12 }}
          />
          <Space>
            <Button onClick={() => setCurrentStep(2)}>← 上一步</Button>
            <Button type="primary" onClick={() => setCurrentStep(4)}>
              下一步 →
            </Button>
          </Space>
        </Card>
      )}

      {/* Step 5: 确认保存 */}
      {currentStep === 4 && (
        <Card type="inner" title="确认并保存">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Title level={5}>节点摘要</Typography.Title>
            <Card size="small" type="inner">
              <div>类型: <Tag>{baseInfo?.node_type}</Tag></div>
              <div>名称: {baseInfo?.name}</div>
              <div>分类: <Tag color="blue">{baseInfo?.category}</Tag></div>
              <div>可见性: <Tag>{baseInfo?.visibility}</Tag></div>
              <div>代码长度: {code.length} 字符</div>
            </Card>
            <Space>
              <Button onClick={() => setCurrentStep(3)}>← 上一步</Button>
              <Button
                type="primary"
                icon={<CheckCircleOutlined />}
                loading={createMutation.isPending}
                onClick={handleSave}
              >
                创建节点
              </Button>
            </Space>
          </Space>
        </Card>
      )}
    </Card>
  );
}
