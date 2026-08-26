/**
 * 动态表单构建器 — 按 ParamSpec 渲染对应控件.
 *
 * 支持类型：str / int / float / bool / select / multiselect / range / list / dict / json / file
 * 高级参数自动折叠（HTML <details>）
 *
 * @see docs/design/04-ui-design.md 4.3
 * @see hscredit.core.spec.ParamSpec
 */

import { Form, Input, InputNumber, Switch, Select, Slider } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import type { ParamSpec } from '@/types';

interface FormBuilderProps {
  params: ParamSpec[];
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
}

export function FormBuilder({ params, values, onChange }: FormBuilderProps) {
  const basicParams = params.filter((p) => !p.advanced);
  const advancedParams = params.filter((p) => p.advanced);

  const renderField = (spec: ParamSpec): React.ReactNode => {
    const value = values[spec.name] ?? spec.default;
    const handleChange = (v: unknown): void => {
      onChange({ ...values, [spec.name]: v });
    };

    switch (spec.type) {
      case 'str':
        return (
          <Input
            value={(value as string | undefined) ?? ''}
            placeholder={spec.placeholder ?? undefined}
            onChange={(e) => handleChange(e.target.value)}
          />
        );
      case 'int':
        return (
          <InputNumber
            value={value as number | undefined}
            min={spec.min ?? undefined}
            max={spec.max ?? undefined}
            step={spec.step ?? 1}
            onChange={(v) => handleChange(v)}
            style={{ width: '100%' }}
          />
        );
      case 'float':
        return (
          <InputNumber
            value={value as number | undefined}
            min={spec.min ?? undefined}
            max={spec.max ?? undefined}
            step={spec.step ?? 0.01}
            onChange={(v) => handleChange(v)}
            style={{ width: '100%' }}
          />
        );
      case 'bool':
        return <Switch checked={Boolean(value)} onChange={handleChange} />;
      case 'select':
        return (
          <Select
            value={value as string | number | undefined}
            onChange={handleChange}
            style={{ width: '100%' }}
            options={(spec.choices ?? []).map((c) => ({ label: c.label, value: c.value as string | number }))}
          />
        );
      case 'multiselect':
        return (
          <Select
            mode="multiple"
            value={(value as unknown[]) ?? []}
            onChange={handleChange}
            style={{ width: '100%' }}
            options={(spec.choices ?? []).map((c) => ({ label: c.label, value: c.value as string | number }))}
          />
        );
      case 'range':
        return (
          <Slider
            min={spec.min ?? 0}
            max={spec.max ?? 100}
            step={spec.step ?? 1}
            value={(value as number | undefined) ?? 0}
            onChange={handleChange}
          />
        );
      case 'list': {
        const current = Array.isArray(value) ? (value as string[]).join('\n') : '';
        return (
          <Input.TextArea
            value={current}
            placeholder="每行一项"
            rows={4}
            onChange={(e) => handleChange(e.target.value.split('\n').filter((s) => s.length > 0))}
          />
        );
      }
      case 'dict':
      case 'json': {
        const text =
          typeof value === 'string'
            ? value
            : value === undefined || value === null
              ? ''
              : JSON.stringify(value, null, 2);
        return (
          <Input.TextArea
            value={text}
            rows={6}
            onChange={(e) => {
              const raw = e.target.value;
              try {
                handleChange(JSON.parse(raw));
              } catch {
                handleChange(raw);
              }
            }}
          />
        );
      }
      case 'file':
        return (
          <Input
            value={(value as string | undefined) ?? ''}
            placeholder="/path/to/file"
            addonAfter={<UploadOutlined />}
            onChange={(e) => handleChange(e.target.value)}
          />
        );
      default:
        return (
          <Input
            value={String(value ?? '')}
            onChange={(e) => handleChange(e.target.value)}
          />
        );
    }
  };

  return (
    <Form layout="vertical">
      {basicParams.map((spec) => (
        <Form.Item
          key={spec.name}
          label={spec.label}
          required={spec.required}
          tooltip={spec.description || undefined}
          valuePropName={spec.type === 'bool' ? 'checked' : 'value'}
        >
          {renderField(spec)}
        </Form.Item>
      ))}
      {advancedParams.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ cursor: 'pointer', marginBottom: 8, color: '#666' }}>
            高级参数 ({advancedParams.length})
          </summary>
          {advancedParams.map((spec) => (
            <Form.Item
              key={spec.name}
              label={spec.label}
              required={spec.required}
              tooltip={spec.description || undefined}
              valuePropName={spec.type === 'bool' ? 'checked' : 'value'}
            >
              {renderField(spec)}
            </Form.Item>
          ))}
        </details>
      )}
    </Form>
  );
}
