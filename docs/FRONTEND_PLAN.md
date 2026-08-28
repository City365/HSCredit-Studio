# HSCredit Studio 前端补齐计划

> 目标: 把后端 121 个 API 端点全部接到前端 UI, 让前端菜单能覆盖 Phase 1-8 所有功能
> 
> 计划日期: 2026-08-28 · 执行人: Claude · 工作目录: `D:\notebook\AIGC\hscredit\frontend`

---

## 1. 现状盘点

### 1.1 前端已存在页面 (7 个)

```
src/pages/
├── auth/Login.tsx
├── workflows/{List,Editor}.tsx
├── runs/{List,Detail}.tsx
├── templates/Gallery.tsx
├── monitor/Dashboard.tsx
├── models/Repository.tsx
└── audit/List.tsx
```

### 1.2 前端 API client (8 个)

```
src/api/
├── auth.ts, workflows.ts, runs.ts, templates.ts, monitor.ts, audit.ts, nodes.ts
└── client.ts (axios + JWT 拦截器 + 401 自动刷新)
```

### 1.3 后端 121 端点 → 前端 0 页面映射 (需补齐 15 个)

| 缺失模块 | 后端 API | 新页面文件 | 优先级 |
|----------|----------|-----------|--------|
| Webhooks | `/webhooks/*` 10 端点 | `pages/webhooks/{List,Detail,Create}.tsx` | P0 (B35 最新) |
| BI Exports | `/bi-exports/*` 8 端点 | `pages/bi-exports/Index.tsx` | P0 (B33 最新) |
| Model Export | `/model-export/*` 4 端点 | `pages/model-export/Index.tsx` | P0 (B34 最新) |
| Industry Templates | `/industry-templates/*` 6 端点 | `pages/industry-templates/Index.tsx` | P1 (B30) |
| Billing | `/bills/*` 5 端点 | `pages/billing/{List,Detail}.tsx` | P1 (B20 发票) |
| Contracts | `/contracts/*` 4 端点 | `pages/contracts/{List,Detail}.tsx` | P1 (B21) |
| Admin Console | `/admin/*` 9 端点 | `pages/admin/Index.tsx` | P1 (B29) |
| Notifications | `/notifications/*` 5 端点 | `pages/notifications/Index.tsx` | P2 (B23) |
| Alerts | `/alerts/*` 7 端点 | `pages/alerts/{Rules,Instances}.tsx` | P2 (B27) |
| Security | `/security/*` 6 端点 | `pages/security/Index.tsx` | P2 (B25) |
| PIPL | `/pipl/*` 6 端点 | `pages/pipl/Index.tsx` | P2 (B26) |
| Data Classification | `/data-classification/*` 3 端点 | `pages/data-classification/Index.tsx` | P2 (B24) |
| RBAC | `/rbac/*` 5 端点 | `pages/rbac/Index.tsx` | P3 (B28) |
| Quota & Usage | `/quota/*` `/usage/*` 3 端点 | `pages/quota/Index.tsx` | P3 (B19/B18) |
| Template Sharing | `/template-sharing/*` 4 端点 | `pages/template-sharing/Index.tsx` | P3 (B31) |

---

## 2. 实施批次 (5 批)

### 批次 1 — 最新功能 (P0) — Webhooks + BI + Model Export

| 步骤 | 内容 | 文件 |
|------|------|------|
| 1.1 | 创建 `src/api/webhooks.ts` (10 端点) | 客户端 |
| 1.2 | 创建 `src/pages/webhooks/List.tsx` (订阅列表 + 创建表单 + 测试按钮) | 页面 |
| 1.3 | 创建 `src/pages/webhooks/Detail.tsx` (订阅详情 + 投递日志 + 重试) | 页面 |
| 1.4 | 创建 `src/api/bi-exports.ts` (8 端点) | 客户端 |
| 1.5 | 创建 `src/pages/bi-exports/Index.tsx` (数据集列表 + 导出表单 + 连接器下载) | 页面 |
| 1.6 | 创建 `src/api/model-export.ts` (4 端点) | 客户端 |
| 1.7 | 创建 `src/pages/model-export/Index.tsx` (演示模型 + 导出 PMML/ONNX + 校验) | 页面 |
| 1.8 | 更新 `router.tsx` 添加 5 个新路由 | 路由 |
| 1.9 | 更新 `Sidebar.tsx` 添加 3 个新菜单项 | 菜单 |
| 1.10 | 前端 lint check | 验证 |

### 批次 2 — 行业模板 + 模板共享 (P1) — 模板生态

| 步骤 | 内容 | 文件 |
|------|------|------|
| 2.1 | 创建 `src/api/industry-templates.ts` | 客户端 |
| 2.2 | 创建 `src/pages/industry-templates/Index.tsx` | 页面 |
| 2.3 | 创建 `src/api/template-sharing.ts` | 客户端 |
| 2.4 | 创建 `src/pages/template-sharing/Index.tsx` | 页面 |
| 2.5 | 更新 router + sidebar | 路由 |

### 批次 3 — 计费/合同/管理 (P1)

| 步骤 | 内容 | 文件 |
|------|------|------|
| 3.1 | 创建 `src/api/billing.ts` + `pages/billing/List.tsx` | 客户端 + 页面 |
| 3.2 | 创建 `src/api/contracts.ts` + `pages/contracts/List.tsx` | 客户端 + 页面 |
| 3.3 | 创建 `src/api/admin.ts` + `pages/admin/Index.tsx` (super_admin) | 客户端 + 页面 |
| 3.4 | 更新 router + sidebar + 角色守卫 | 路由 |

### 批次 4 — 合规与安全 (P2)

| 步骤 | 内容 | 文件 |
|------|------|------|
| 4.1 | 创建 `src/api/notifications.ts` + `pages/notifications/Index.tsx` | 客户端 + 页面 |
| 4.2 | 创建 `src/api/alerts.ts` + `pages/alerts/{Rules,Instances}.tsx` | 客户端 + 页面 |
| 4.3 | 创建 `src/api/security.ts` + `pages/security/Index.tsx` | 客户端 + 页面 |
| 4.4 | 创建 `src/api/pipl.ts` + `pages/pipl/Index.tsx` | 客户端 + 页面 |
| 4.5 | 创建 `src/api/data-classification.ts` + `pages/data-classification/Index.tsx` | 客户端 + 页面 |
| 4.6 | 更新 router + sidebar | 路由 |

### 批次 5 — RBAC + 用量 (P3)

| 步骤 | 内容 | 文件 |
|------|------|------|
| 5.1 | 创建 `src/api/rbac.ts` + `pages/rbac/Index.tsx` | 客户端 + 页面 |
| 5.2 | 创建 `src/api/quota.ts` + `pages/quota/Index.tsx` (含 usage) | 客户端 + 页面 |
| 5.3 | 更新 router + sidebar | 路由 |

---

## 3. 实施模式 (统一模板)

每个新模块严格按以下顺序:

### 3.1 API client 模板 (例: webhooks.ts)

```typescript
import { apiClient } from './client';

export interface WebhookSubscription {
  subscription_id: string;
  tenant_id: string;
  url: string;
  events: string[];
  active: boolean;
  description: string;
  created_at: string;
}

export const webhooksApi = {
  listEvents: () => apiClient.get<{ events: any[]; total: number }>('/webhooks/events'),
  listSubscriptions: () => apiClient.get<{ items: WebhookSubscription[]; total: number }>('/webhooks/subscriptions'),
  createSubscription: (data: { url: string; events: string[]; description?: string }) =>
    apiClient.post<WebhookSubscription & { secret: string }>('/webhooks/subscriptions', data),
  getSubscription: (id: string) => apiClient.get<WebhookSubscription>(`/webhooks/subscriptions/${id}`),
  testSubscription: (id: string) => apiClient.post<{ success: boolean; response_status: number | null; error: string | null }>(`/webhooks/subscriptions/${id}/test`),
  listDeliveries: (id: string) => apiClient.get<{ items: any[]; total: number }>(`/webhooks/subscriptions/${id}/deliveries`),
  retryDelivery: (deliveryId: string) => apiClient.post(`/webhooks/deliveries/${deliveryId}/retry`),
  publishEvent: (event: string, payload: any) => apiClient.post('/webhooks/publish', { event, payload }),
  verifySignature: (data: { secret: string; payload: string; signature: string; timestamp: number }) =>
    apiClient.post<{ valid: boolean }>('/webhooks/verify-signature', data),
};
```

### 3.2 页面模板 (例: List.tsx)

```typescript
import { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Select, message, Tag, Space, Card } from 'antd';
import { PlusOutlined, ReloadOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { webhooksApi, type WebhookSubscription } from '@/api/webhooks';

export function WebhooksList(): React.ReactElement {
  const [items, setItems] = useState<WebhookSubscription[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  useEffect(() => { load(); loadEvents(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const d = await webhooksApi.listSubscriptions();
      setItems(d.items);
    } finally { setLoading(false); }
  };

  // ... 渲染 + 表单 + 测试按钮
}
```

### 3.3 路由注册 (router.tsx)

```typescript
const WebhooksList = lazy(() => import('./pages/webhooks/List'));
// ...
{ path: 'webhooks', element: <Suspense fallback={<Loading />}><WebhooksList /></Suspense> },
```

### 3.4 Sidebar 菜单

```typescript
{
  key: '/webhooks',
  icon: <WebhookOutlined />,
  label: 'Webhooks',
  onClick: () => navigate('/webhooks'),
},
```

---

## 4. 验证清单

每批完成后:

- [ ] TypeScript 编译: `npm run type-check` 退出码 0
- [ ] ESLint: `npm run lint` 退出码 0
- [ ] 浏览器打开 http://localhost:3000, 登录后能在侧边栏看到新菜单
- [ ] 点击新菜单能进入页面, 不出现白屏/转圈
- [ ] API 调用成功, 数据显示正确

---

## 5. 范围控制

- 不重写已有页面, 只新增
- 复用 `api/client.ts` 的 axios 实例 + JWT 拦截器
- 复用 `components/Layout/AppLayout.tsx` 布局
- 复用 i18n (`useTranslation`)
- 复用 antd 组件库
- 每页保持 100-200 行, 不写长逻辑
- 列表页用 antd `Table` + `useQuery` (TanStack Query, 已在 main.tsx 配置)

---

## 6. 提交策略

每个批次完成后:

```bash
git add frontend/src/{api,pages,components/layout,router.tsx}
git commit -m "feat(frontend): 批次 N - <页面列表>"
git push
```

---

## 7. 风险

- **API 返回结构不一致**: 某些端点可能用 `items`/`total`, 某些可能用 `data`. 用例驱动, 看到不一致就改 client.
- **类型不匹配**: 后端返回 snake_case, 前端用 camelCase. 在 API 层做转换.
- **CORS**: 已经在 main.py 加过 CORSAlwaysMiddleware, 应该没问题.

---

## 8. 验收标准

✅ 侧边栏包含 15+ 个菜单项 (覆盖 Phase 1-8)
✅ 所有页面能正常访问 + 显示数据
✅ `npm run type-check` 通过
✅ `npm run lint` 通过
✅ 后端 121 端点全部可从 UI 触发