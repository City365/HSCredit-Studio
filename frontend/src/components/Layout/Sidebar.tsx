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
  CloudDownloadOutlined,
  ExportOutlined,
  ApiOutlined,
  ShopOutlined,
  ShareAltOutlined,
  FileTextOutlined,
  FileProtectOutlined,
  CrownOutlined,
  BellOutlined,
  AlertOutlined,
  SafetyOutlined,
  UserSwitchOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
  DashboardOutlined,
  ExperimentOutlined,
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
    {
      key: '/nodes',
      icon: <ExperimentOutlined />,
      label: t('menu.nodes', '节点管理'),
      onClick: () => navigate('/nodes'),
    },
    // 批次 1 新菜单 (Phase 7-8)
    {
      key: '/bi-exports',
      icon: <CloudDownloadOutlined />,
      label: 'BI 报表导出',
      onClick: () => navigate('/bi-exports'),
    },
    {
      key: '/model-export',
      icon: <ExportOutlined />,
      label: '模型导出',
      onClick: () => navigate('/model-export'),
    },
    {
      key: '/webhooks',
      icon: <ApiOutlined />,
      label: 'Webhooks',
      onClick: () => navigate('/webhooks'),
    },
    // 批次 2 (模板生态)
    {
      key: '/industry-templates',
      icon: <ShopOutlined />,
      label: '行业模板市场',
      onClick: () => navigate('/industry-templates'),
    },
    {
      key: '/template-sharing',
      icon: <ShareAltOutlined />,
      label: '模板共享',
      onClick: () => navigate('/template-sharing'),
    },
    // 批次 3 (计费/合同/管理)
    {
      key: '/billing',
      icon: <FileTextOutlined />,
      label: '账单管理',
      onClick: () => navigate('/billing'),
    },
    {
      key: '/contracts',
      icon: <FileProtectOutlined />,
      label: '合同管理',
      onClick: () => navigate('/contracts'),
    },
    {
      key: '/admin',
      icon: <CrownOutlined />,
      label: '超管后台',
      onClick: () => navigate('/admin'),
    },
    // 批次 4 (合规安全)
    {
      key: '/notifications',
      icon: <BellOutlined />,
      label: '通知配置',
      onClick: () => navigate('/notifications'),
    },
    {
      key: '/alerts',
      icon: <AlertOutlined />,
      label: '告警管理',
      onClick: () => navigate('/alerts'),
    },
    {
      key: '/security',
      icon: <SafetyCertificateOutlined />,
      label: '安全运营',
      onClick: () => navigate('/security'),
    },
    {
      key: '/pipl',
      icon: <UserSwitchOutlined />,
      label: 'PIPL 数据保护',
      onClick: () => navigate('/pipl'),
    },
    {
      key: '/data-classification',
      icon: <LockOutlined />,
      label: '数据脱敏',
      onClick: () => navigate('/data-classification'),
    },
    // 批次 5 (RBAC + 用量)
    {
      key: '/rbac',
      icon: <SafetyOutlined />,
      label: 'RBAC 权限',
      onClick: () => navigate('/rbac'),
    },
    {
      key: '/quota',
      icon: <DashboardOutlined />,
      label: '配额与用量',
      onClick: () => navigate('/quota'),
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
