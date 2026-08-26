/**
 * 认证状态管理 — Zustand + persist.
 *
 * 持久化键：localStorage 'hscredit-auth'
 * 仅持久化 token / user / tenant / role，**不**持久化函数.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

import type { TokenPair, UserInfo } from '@/types';

/**
 * AuthState 接口.
 *
 * - `accessToken` / `refreshToken`: JWT 对
 * - `user`: 用户信息
 * - `tenantSlug` / `role`: 当前租户与角色（用于 URL 注入与权限检查）
 */
interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: UserInfo | null;
  tenantSlug: string | null;
  role: string | null;

  // ---- Actions ----
  setTokens: (access: string, refresh: string) => void;
  setUser: (user: UserInfo) => void;
  setTenant: (slug: string, role: string) => void;
  setAuth: (tokens: TokenPair, user: UserInfo, tenantSlug: string, role: string) => void;
  clearAuth: () => void;

  // ---- Computed ----
  isAuthenticated: () => boolean;
  hasRole: (...roles: string[]) => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      tenantSlug: null,
      role: null,

      setTokens: (access, refresh) => set({ accessToken: access, refreshToken: refresh }),

      setUser: (user) => set({ user }),

      setTenant: (slug, role) => set({ tenantSlug: slug, role }),

      setAuth: (tokens, user, tenantSlug, role) =>
        set({
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
          user,
          tenantSlug,
          role,
        }),

      clearAuth: () =>
        set({
          accessToken: null,
          refreshToken: null,
          user: null,
          tenantSlug: null,
          role: null,
        }),

      isAuthenticated: () => {
        const state = get();
        return !!(state.accessToken && state.user && state.tenantSlug);
      },

      hasRole: (...roles) => {
        const state = get();
        if (!state.role) return false;
        return roles.includes(state.role);
      },
    }),
    {
      name: 'hscredit-auth',
      storage: createJSONStorage(() => localStorage),
      /** 仅持久化必要字段，函数不写入存储. */
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
        tenantSlug: state.tenantSlug,
        role: state.role,
      }),
      /** 版本号用于未来 schema 迁移. */
      version: 1,
    },
  ),
);

/** 选择器便捷访问. */
export const selectAccessToken = (s: AuthState): string | null => s.accessToken;
export const selectRefreshToken = (s: AuthState): string | null => s.refreshToken;
export const selectTenantSlug = (s: AuthState): string | null => s.tenantSlug;
export const selectUser = (s: AuthState): UserInfo | null => s.user;