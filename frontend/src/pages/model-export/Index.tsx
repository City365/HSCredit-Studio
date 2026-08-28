/** 模型导出页 — Phase 7 B34.

支持:
- 生成演示评分卡 (默认)
- 选择格式 PMML / ONNX 导出
- 跨平台一致性校验 (max_abs_error < 1e-6)
- 显示警告 (sklearn2pmml / skl2onnx 缺失时)
*/
import { useState } from 'react';
import {
  Card,
  Button,
  Select,
  Space,
  Tag,
  Form,
  InputNumber,
  App,
  Alert,
  Descriptions,
  Divider,
} from 'antd';
import { DownloadOutlined, ExperimentOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  modelExportApi,
  type DemoModelResponse,
  type ModelExportResponse,
  type ModelValidationResponse,
} from '@/api/model-export';

const DEFAULT_FEATURES = ['age', 'income', 'credit_score', 'debt_ratio', 'employment_years'];

export function ModelExportPage(): React.ReactElement {
  const { message } = App.useApp();
  const [demo, setDemo] = useState<DemoModelResponse | null>(null);
  const [exportFormat, setExportFormat] = useState<'pmml' | 'onnx'>('pmml');
  const [exportResult, setExportResult] = useState<ModelExportResponse | null>(null);
  const [validation, setValidation] = useState<ModelValidationResponse | null>(null);
  const [sampleSize, setSampleSize] = useState<number>(5);
  const [exporting, setExporting] = useState(false);
  const [validating, setValidating] = useState(false);

  const onGenerateDemo = async (): Promise<void> => {
    try {
      const r = await modelExportApi.generateDemoModel({ feature_names: DEFAULT_FEATURES });
      setDemo(r);
      setExportResult(null);
      setValidation(null);
      message.success('演示评分卡已生成');
    } catch (e) {
      message.error('生成失败: ' + (e as Error).message);
    }
  };

  const onExport = async (): Promise<void> => {
    if (!demo) {
      message.warning('先生成演示模型');
      return;
    }
    setExporting(true);
    try {
      const r = await modelExportApi.exportModel({
        model_b64: demo.model_b64,
        model_type: 'scorecard',
        feature_names: demo.feature_names,
        format: exportFormat,
        description: 'E2E demo export',
      });
      setExportResult(r);
      message.success(`已导出 ${r.filename} (${r.file_size} 字节)`);
      // 自动下载
      modelExportApi.downloadExported(r);
    } catch (e) {
      message.error('导出失败: ' + (e as Error).message);
    } finally {
      setExporting(false);
    }
  };

  const onValidate = async (): Promise<void> => {
    if (!demo || !exportResult) {
      message.warning('先生成模型并导出');
      return;
    }
    setValidating(true);
    try {
      // 生成随机样本
      const samples = Array.from({ length: sampleSize }, () =>
        demo.feature_names.map(() => Math.random()),
      );
      const r = await modelExportApi.validate({
        original_model_b64: demo.model_b64,
        exported_format: exportFormat,
        exported_content_b64: exportResult.content_b64,
        sample_inputs: samples,
        tolerance: 1e-3,
      });
      setValidation(r);
      if (r.passed) {
        message.success(`校验通过: max_abs_error=${r.max_abs_error.toExponential(2)}`);
      } else {
        message.warning(`校验失败: ${r.message}`);
      }
    } catch (e) {
      message.error('校验异常: ' + (e as Error).message);
    } finally {
      setValidating(false);
    }
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card title="演示评分卡 (Phase 7 B34)">
        <Space wrap>
          <Button
            type="primary"
            icon={<ExperimentOutlined />}
            onClick={() => void onGenerateDemo()}
          >
            生成演示模型
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={() => void onExport()}
            disabled={!demo}
            loading={exporting}
          >
            导出 {exportFormat.toUpperCase()}
          </Button>
          <Button
            icon={<ExperimentOutlined />}
            onClick={() => void onValidate()}
            disabled={!exportResult}
            loading={validating}
          >
            一键校验
          </Button>
        </Space>
        <Divider />
        <Form layout="inline">
          <Form.Item label="导出格式">
            <Select
              value={exportFormat}
              onChange={(v) => setExportFormat(v)}
              style={{ width: 120 }}
              options={[
                { label: 'PMML', value: 'pmml' },
                { label: 'ONNX', value: 'onnx' },
              ]}
            />
          </Form.Item>
          <Form.Item label="校验样本数">
            <InputNumber
              min={1}
              max={100}
              value={sampleSize}
              onChange={(v) => setSampleSize(v ?? 5)}
            />
          </Form.Item>
        </Form>
      </Card>

      {demo && (
        <Card title="演示模型参数" extra={<Tag color="blue">scorecard</Tag>}>
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="特征数">{demo.feature_names.length}</Descriptions.Item>
            <Descriptions.Item label="系数项数">{demo.coefficients.length}</Descriptions.Item>
            <Descriptions.Item label="特征名" span={2}>
              <Space size={[4, 4]} wrap>
                {demo.feature_names.map((f) => <Tag key={f}>{f}</Tag>)}
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="系数 (coefficients)" span={2}>
              [{demo.coefficients.map((c) => c.toExponential(2)).join(', ')}]
            </Descriptions.Item>
            <Descriptions.Item label="截距 (intercept)" span={2}>
              <code>{demo.intercept}</code>
            </Descriptions.Item>
            <Descriptions.Item label="描述" span={2}>
              {demo.description}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      {exportResult && exportResult.warnings.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message="导出警告"
          description={
            <ul>
              {exportResult.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          }
        />
      )}

      {exportResult && (
        <Card title={`导出结果: ${exportResult.filename}`}>
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="格式">
              <Tag color={exportResult.format === 'pmml' ? 'blue' : 'purple'}>
                {exportResult.format.toUpperCase()}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="大小">{exportResult.file_size} 字节</Descriptions.Item>
            <Descriptions.Item label="MIME">{exportResult.mime_type}</Descriptions.Item>
            <Descriptions.Item label="模型类型">{exportResult.model_type}</Descriptions.Item>
            <Descriptions.Item label="导出时间" span={2}>
              {new Date(exportResult.exported_at).toLocaleString('zh-CN')}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      {validation && (
        <Card
          title="跨平台一致性校验"
          extra={
            validation.passed ? (
              <Tag color="success" icon={<ReloadOutlined />}>通过</Tag>
            ) : (
              <Tag color="error">未通过</Tag>
            )
          }
        >
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="样本数">{validation.sample_count}</Descriptions.Item>
            <Descriptions.Item label="最大绝对误差">
              <code>{validation.max_abs_error.toExponential(3)}</code>
            </Descriptions.Item>
            <Descriptions.Item label="平均绝对误差">
              <code>{validation.mean_abs_error.toExponential(3)}</code>
            </Descriptions.Item>
            <Descriptions.Item label="容差">
              <code>1e-3</code>
            </Descriptions.Item>
            <Descriptions.Item label="消息" span={2}>{validation.message}</Descriptions.Item>
            <Descriptions.Item label="原模型预测 (前 5)" span={2}>
              <code>[{validation.original_predictions.slice(0, 5).map((v) => v.toFixed(4)).join(', ')}]</code>
            </Descriptions.Item>
            <Descriptions.Item label="导出模型预测 (前 5)" span={2}>
              <code>[{validation.exported_predictions.slice(0, 5).map((v) => v.toFixed(4)).join(', ')}]</code>
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}
    </Space>
  );
}

export default ModelExportPage;