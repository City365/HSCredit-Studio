/**
 * 应用根组件.
 *
 * QueryClient + ConfigProvider 已在 main.tsx 提供，此处仅挂载 RouterProvider.
 * 子路由的 Suspense 由 router.tsx 在每个路由段粒度上控制.
 */

import { RouterProvider } from 'react-router-dom';
import { router } from './router';

export default function App() {
  return <RouterProvider router={router} />;
}
