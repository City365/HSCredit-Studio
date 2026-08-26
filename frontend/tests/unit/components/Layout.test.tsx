/**
 * AppLayout 组件 smoke test.
 *
 * 注意：本测试 mock 掉 authStore，避免依赖全局 zustand 状态。
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppLayout } from '@/components/Layout/AppLayout';

// Mock authStore — 隔离 store 状态
vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({
    user: {
      user_id: 'u1',
      email: 'a@b.com',
      display_name: 'Admin',
      status: 'active',
      locale: 'zh-CN',
    },
    tenantSlug: 'demo',
    role: 'owner',
    clearAuth: vi.fn(),
  }),
}));

describe('AppLayout', () => {
  it('renders sidebar and header', () => {
    render(
      <MemoryRouter>
        <AppLayout />
      </MemoryRouter>,
    );
    expect(screen.getByText('HSCredit')).toBeInTheDocument();
    expect(screen.getByText('Admin')).toBeInTheDocument();
    expect(screen.getByText('demo')).toBeInTheDocument();
  });
});