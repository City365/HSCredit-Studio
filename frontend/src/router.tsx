/**
 * 路由配置（懒加载 + RequireAuth 守卫）.
 *
 * @see docs/design/04-ui-design.md
 *
 * 关键修复（批次 8）：
 *   - 原本懒加载的 AppLayout 改为同步导入（认证守卫包裹 Lazy 子路由）
 *   - 增加 RequireAuth 守卫组件：未登录重定向到 /login
 *   - 全部业务页面通过 Suspense + lazy 分包
 */

import { lazy, Suspense } from 'react';
import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom';
import { Spin } from 'antd';
import { AppLayout } from './components/Layout/AppLayout';
import { useAuthStore } from './stores/authStore';

const Login = lazy(() => import('./pages/auth/Login'));
const WorkflowList = lazy(() => import('./pages/workflows/List'));
const WorkflowEditor = lazy(() => import('./pages/workflows/Editor'));
const RunList = lazy(() => import('./pages/runs/List'));
const RunDetail = lazy(() => import('./pages/runs/Detail'));
const TemplateGallery = lazy(() => import('./pages/templates/Gallery'));
const MonitorDashboard = lazy(() => import('./pages/monitor/Dashboard'));
const ModelRepository = lazy(() => import('./pages/models/Repository'));
const AuditPage = lazy(() => import('./pages/audit/List'));
const NotFound = lazy(() => import('./pages/NotFound'));
// 批次 1 (Phase 7-8 新功能前端)
const WebhooksList = lazy(() => import('./pages/webhooks/List'));
const WebhookDetail = lazy(() => import('./pages/webhooks/Detail'));
const BIExportsPage = lazy(() => import('./pages/bi-exports/Index'));
const ModelExportPage = lazy(() => import('./pages/model-export/Index'));
// 批次 2-5 (Phase 4-6 功能前端)
const IndustryTemplatesPage = lazy(() => import('./pages/industry-templates/Index'));
const TemplateSharingPage = lazy(() => import('./pages/template-sharing/Index'));
const BillingListPage = lazy(() => import('./pages/billing/List'));
const ContractsListPage = lazy(() => import('./pages/contracts/List'));
const AdminPage = lazy(() => import('./pages/admin/Index'));
const NotificationsPage = lazy(() => import('./pages/notifications/Index'));
const AlertsPage = lazy(() => import('./pages/alerts/Index'));
const SecurityPage = lazy(() => import('./pages/security/Index'));
const PiplPage = lazy(() => import('./pages/pipl/Index'));
const DataClassificationPage = lazy(() => import('./pages/data-classification/Index'));
const RbacPage = lazy(() => import('./pages/rbac/Index'));
const QuotaPage = lazy(() => import('./pages/quota/Index'));

const Loading = (): React.ReactElement => (
  <div
    style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '100vh',
    }}
  >
    <Spin size="large" />
  </div>
);

/**
 * 认证守卫 — 未登录跳转到 /login.
 */
function RequireAuth({ children }: { children: React.ReactNode }): React.ReactElement {
  const isAuthenticatedFn = useAuthStore((s) => s.isAuthenticated);
  if (!isAuthenticatedFn()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

export const router = createBrowserRouter([
  // 登录
  { path: '/login', element: <Suspense fallback={<Loading />}><Login /></Suspense> },

  // 受保护路由（外层 RequireAuth + 内层 AppLayout）
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="/workflows" replace /> },
      { path: 'workflows', element: <Suspense fallback={<Loading />}><WorkflowList /></Suspense> },
      { path: 'workflows/new', element: <Suspense fallback={<Loading />}><WorkflowEditor /></Suspense> },
      { path: 'workflows/:id', element: <Suspense fallback={<Loading />}><WorkflowEditor /></Suspense> },
      { path: 'runs', element: <Suspense fallback={<Loading />}><RunList /></Suspense> },
      { path: 'runs/:id', element: <Suspense fallback={<Loading />}><RunDetail /></Suspense> },
      { path: 'templates', element: <Suspense fallback={<Loading />}><TemplateGallery /></Suspense> },
      { path: 'monitor', element: <Suspense fallback={<Loading />}><MonitorDashboard /></Suspense> },
      { path: 'models', element: <Suspense fallback={<Loading />}><ModelRepository /></Suspense> },
      { path: 'audit', element: <Suspense fallback={<Loading />}><AuditPage /></Suspense> },
      // 批次 1 新路由 (Phase 7-8)
      { path: 'webhooks', element: <Suspense fallback={<Loading />}><WebhooksList /></Suspense> },
      { path: 'webhooks/:id', element: <Suspense fallback={<Loading />}><WebhookDetail /></Suspense> },
      { path: 'bi-exports', element: <Suspense fallback={<Loading />}><BIExportsPage /></Suspense> },
      { path: 'model-export', element: <Suspense fallback={<Loading />}><ModelExportPage /></Suspense> },
      // 批次 2-5
      { path: 'industry-templates', element: <Suspense fallback={<Loading />}><IndustryTemplatesPage /></Suspense> },
      { path: 'template-sharing', element: <Suspense fallback={<Loading />}><TemplateSharingPage /></Suspense> },
      { path: 'billing', element: <Suspense fallback={<Loading />}><BillingListPage /></Suspense> },
      { path: 'contracts', element: <Suspense fallback={<Loading />}><ContractsListPage /></Suspense> },
      { path: 'admin', element: <Suspense fallback={<Loading />}><AdminPage /></Suspense> },
      { path: 'notifications', element: <Suspense fallback={<Loading />}><NotificationsPage /></Suspense> },
      { path: 'alerts', element: <Suspense fallback={<Loading />}><AlertsPage /></Suspense> },
      { path: 'security', element: <Suspense fallback={<Loading />}><SecurityPage /></Suspense> },
      { path: 'pipl', element: <Suspense fallback={<Loading />}><PiplPage /></Suspense> },
      { path: 'data-classification', element: <Suspense fallback={<Loading />}><DataClassificationPage /></Suspense> },
      { path: 'rbac', element: <Suspense fallback={<Loading />}><RbacPage /></Suspense> },
      { path: 'quota', element: <Suspense fallback={<Loading />}><QuotaPage /></Suspense> },
    ],
  },

  // 404
  { path: '*', element: <Suspense fallback={<Loading />}><NotFound /></Suspense> },
]);

// suppress unused-import warning for Outlet (kept for future nested layouts)
export { Outlet };
