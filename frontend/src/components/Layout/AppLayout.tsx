/**
 * 整体应用布局（Sider + Header + Content）.
 *
 * - 左侧 Sider：菜单导航（Sidebar）
 * - 顶部 Header：租户信息 + 用户菜单（登出）
 * - 主区域：<Outlet /> 渲染子路由
 *
 * @see docs/design/04-ui-design.md 4.1
 */

import { Layout, Dropdown, Avatar, Space, Typography } from 'antd';
import { Outlet, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  UserOutlined,
  LogoutOutlined,
  CaretDownOutlined,
  ProfileOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '@/stores/authStore';
import { Sidebar } from './Sidebar';

const { Header, Sider, Content } = Layout;

export function AppLayout() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = window.location;
  const user = useAuthStore((s) => s.user);
  const tenantSlug = useAuthStore((s) => s.tenantSlug);
  const role = useAuthStore((s) => s.role);
  const clearAuth = useAuthStore((s) => s.clearAuth);

  const handleLogout = (): void => {
    clearAuth();
    navigate('/login');
  };

  const userMenu = [
    {
      key: 'profile',
      label: t('menu.profile', '个人中心'),
      icon: <ProfileOutlined />,
      onClick: (): void => navigate('/profile'),
    },
    { type: 'divider' as const },
    {
      key: 'logout',
      label: t('auth.logout'),
      icon: <LogoutOutlined />,
      onClick: handleLogout,
    },
  ];

  // 从当前 URL 路径推断 Sidebar 选中项（取最长前缀匹配）
  const selectedKey = ((): string => {
    const path = location.pathname;
    const candidates = ['/workflows', '/runs', '/templates', '/monitor', '/models'];
    for (const c of candidates) {
      if (path === c || path.startsWith(`${c}/`)) return c;
    }
    return '/workflows';
  })();

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} theme="dark">
        <div
          style={{
            height: 48,
            margin: 16,
            color: '#fff',
            fontSize: 18,
            fontWeight: 'bold',
            textAlign: 'center',
            lineHeight: '48px',
          }}
        >
          HSCredit
        </div>
        <Sidebar selectedKey={selectedKey} />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 16px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            boxShadow: '0 1px 4px rgba(0, 21, 41, 0.08)',
          }}
        >
          <Space>
            <Typography.Text type="secondary">{t('header.tenant', '当前租户')}:</Typography.Text>
            <strong>{tenantSlug ?? '-'}</strong>
            {role && (
              <Typography.Text type="secondary" style={{ marginLeft: 16 }}>
                ({role})
              </Typography.Text>
            )}
          </Space>
          <Dropdown menu={{ items: userMenu }} trigger={['click']}>
            <Space style={{ cursor: 'pointer' }}>
              <Avatar icon={<UserOutlined />} />
              <span>{user?.display_name ?? 'User'}</span>
              <CaretDownOutlined />
            </Space>
          </Dropdown>
        </Header>
        <Content
          style={{
            margin: 16,
            padding: 16,
            background: '#fff',
            borderRadius: 8,
            minHeight: 280,
            overflow: 'auto',
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
