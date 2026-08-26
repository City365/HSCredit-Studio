/**
 * 认证 API.
 *
 * 注意：登录、刷新、登出三类请求由 `client.ts` 拦截器识别 `/auth/` 前缀后
 * 自动跳过 tenant slug 注入；登录请求本身也不需要 Authorization 头（store 此时尚为空）.
 */

import { apiClient } from './client';
import type { LoginRequest, LoginResponse, TokenPair } from '@/types';

export const authApi = {
  /** 邮箱 + 密码 + tenant_slug 登录. */
  login: async (req: LoginRequest): Promise<LoginResponse> => {
    const response = await apiClient.post<LoginResponse>('/auth/login', req);
    return response.data;
  },

  /** 使用 refresh_token 刷新 access_token. */
  refresh: async (refreshToken: string): Promise<TokenPair> => {
    const response = await apiClient.post<TokenPair>('/auth/refresh', {
      refresh_token: refreshToken,
    });
    return response.data;
  },

  /** 主动登出（撤销 refresh_token）.*/
  logout: async (refreshToken: string): Promise<void> => {
    await apiClient.post<void>('/auth/logout', { refresh_token: refreshToken });
  },
};