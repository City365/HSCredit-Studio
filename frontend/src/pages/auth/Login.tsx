/**
 * 登录页面 — 邮箱 + 密码 + tenant_slug.
 *
 * 登录成功后调用 setAuth() 写入 token + user + tenant，
 * 然后跳转到 /workflows.
 */

import { useState } from 'react';
import { Form, Input, Button, Card, Typography, message } from 'antd';
import { useNavigate, Navigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { authApi } from '@/api/auth';
import { useAuthStore } from '@/stores/authStore';
import type { LoginRequest } from '@/types';

export default function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const checkAuth = useAuthStore((s) => s.isAuthenticated);
  const isAuthenticated = checkAuth();
  const [form] = Form.useForm<LoginRequest>();
  const [loading, setLoading] = useState(false);

  // 已登录则直接跳转
  if (isAuthenticated) {
    return <Navigate to="/workflows" replace />;
  }

  const onFinish = async (values: LoginRequest): Promise<void> => {
    setLoading(true);
    try {
      const resp = await authApi.login(values);
      setAuth(resp.tokens, resp.user, resp.tenant_slug, resp.role);
      message.success(t('auth.loginSuccess', '登录成功'));
      navigate('/workflows');
    } catch (err: unknown) {
      const error = err as { message?: string };
      message.error(error.message ?? t('auth.loginFailed', '登录失败'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f0f2f5',
      }}
    >
      <Card style={{ width: 400 }} title={null}>
        <Typography.Title level={3} style={{ textAlign: 'center', margin: 0, marginBottom: 24 }}>
          HSCredit 建模工作台
        </Typography.Title>
        <Form<LoginRequest>
          form={form}
          layout="vertical"
          onFinish={onFinish}
          initialValues={{ tenant_slug: 'demo' }}
          requiredMark={false}
        >
          <Form.Item
            name="tenant_slug"
            label={t('auth.tenant', '租户')}
            rules={[{ required: true, message: '请输入租户' }]}
          >
            <Input placeholder="demo" autoComplete="organization" />
          </Form.Item>
          <Form.Item
            name="email"
            label={t('auth.email')}
            rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}
          >
            <Input placeholder="user@example.com" autoComplete="email" />
          </Form.Item>
          <Form.Item
            name="password"
            label={t('auth.password')}
            rules={[{ required: true, min: 8, message: '密码至少 8 位' }]}
          >
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" loading={loading} block>
              {t('auth.login')}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
