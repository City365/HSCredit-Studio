/**
 * 侧边栏菜单导航.
 *
 * @see docs/design/04-ui-design.md 4.1
 */

import { Menu } from 'antd';
import type { MenuProps } from 'antd';
import {
  ApartmentOutlined,
  ThunderboltOutlined,
  AppstoreOutlined,
  MonitorOutlined,
  DatabaseOutlined,
  AuditOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

interface SidebarProps {
  selectedKey: string;
}

type MenuItem = NonNullable<MenuProps['items']>[number];

export function Sidebar({ selectedKey }: SidebarProps) {
  const navigate = useNavigate();
  const { t } = useTranslation();

  const items: MenuItem[] = [
    {
      key: '/workflows',
      icon: <ApartmentOutlined />,
      label: t('menu.workflows'),
      onClick: () => navigate('/workflows'),
    },
    {
      key: '/runs',
      icon: <ThunderboltOutlined />,
      label: t('menu.runs'),
      onClick: () => navigate('/runs'),
    },
    {
      key: '/templates',
      icon: <AppstoreOutlined />,
      label: t('menu.templates'),
      onClick: () => navigate('/templates'),
    },
    {
      key: '/monitor',
      icon: <MonitorOutlined />,
      label: t('menu.monitor'),
      onClick: () => navigate('/monitor'),
    },
    {
      key: '/models',
      icon: <DatabaseOutlined />,
      label: t('menu.models'),
      onClick: () => navigate('/models'),
    },
    {
      key: '/audit',
      icon: <AuditOutlined />,
      label: t('menu.audit', '审计日志'),
      onClick: () => navigate('/audit'),
    },
  ];

  return (
    <Menu
      theme="dark"
      mode="inline"
      selectedKeys={[selectedKey]}
      items={items}
      style={{ borderRight: 0 }}
    />
  );
}
