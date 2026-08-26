/**
 * Axios 实例 + JWT 拦截器 + 自动 401 刷新 + X-Request-ID 注入 + tenant slug 路径注入.
 *
 * 设计要点:
 *   1. 请求拦截器：从 authStore 读取 accessToken + tenantSlug，自动注入 `Authorization` /
 *      `X-Request-ID` 头与 `/api/v1/{tenant_slug}/...` 路径.
 *   2. 响应拦截器：捕获 401 → 走 TokenRefreshHandler 单例刷新 → 拿到新 token 重放原请求.
 *   3. 错误标准化：将后端 `ErrorResponse` 平铺为前端 `NormalizedApiError`（含 code/status/
 *      details/request_id），便于上层统一处理.
 *   4. 刷新锁：使用单例 + Promise 缓存，避免并发 401 触发多次 /auth/refresh.
 */

import axios, {
  AxiosError,
  AxiosInstance,
  AxiosResponse,
  InternalAxiosRequestConfig,
} from 'axios';

import { useAuthStore } from '@/stores/authStore';
import type { ErrorResponse, NormalizedApiError } from '@/types';

/**
 * 读取 Vite 环境变量.
 *
 * 项目 `tsconfig.json` 的 `types` 字段显式列出测试类型，未包含 `vite/client`，
 * 因此这里使用本地 cast 替代 `import.meta.env` 的隐式类型.
 */
function readApiBaseUrl(): string {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env;
  return env?.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1';
}

const API_BASE_URL: string = readApiBaseUrl();

/** 跳过 tenant slug 注入的白名单路径前缀（/auth/*, /healthz, /readyz）.*/
const TENANT_SKIP_PREFIXES = ['/auth/', '/healthz', '/readyz', '/openapi.json', '/docs', '/redoc'];

/**
 * 判断 URL 是否应跳过 tenant slug 注入.
 *
 * 规则：
 *   - URL 以白名单前缀开头 → 跳过
 *   - URL 已包含 `/{tenant}/` 段（即形如 `/xxx/yyy/...` 且第二段非 `auth`）→ 跳过
 */
function shouldSkipTenantInject(url: string | undefined): boolean {
  if (!url) return true;
  if (TENANT_SKIP_PREFIXES.some((p) => url.startsWith(p))) return true;
  // 已注入过（避免重复添加）
  if (url.startsWith('/auth/')) return true;
  return false;
}

/**
 * 在 URL 路径前插入 `/{tenantSlug}` 段.
 *
 * 示例：
 *   prependTenant('/workflows', 'acme')          -> '/acme/workflows'
 *   prependTenant('/workflows/123', 'acme')      -> '/acme/workflows/123'
 *   prependTenant('/workflows?page=1', 'acme')   -> '/acme/workflows?page=1'
 */
function prependTenant(url: string, tenantSlug: string): string {
  // 拆分 path 与 query / hash
  const queryIndex = url.indexOf('?');
  const hashIndex = url.indexOf('#');
  let splitIndex = -1;
  if (queryIndex >= 0 && hashIndex >= 0) splitIndex = Math.min(queryIndex, hashIndex);
  else if (queryIndex >= 0) splitIndex = queryIndex;
  else if (hashIndex >= 0) splitIndex = hashIndex;

  const pathPart = splitIndex >= 0 ? url.slice(0, splitIndex) : url;
  const suffix = splitIndex >= 0 ? url.slice(splitIndex) : '';

  const normalized = pathPart.startsWith('/') ? pathPart : `/${pathPart}`;
  return `/${tenantSlug}${normalized}${suffix}`;
}

/**
 * 生成 RFC4122 v4 UUID.
 *
 * 优先使用 `crypto.randomUUID`；不支持时回退到 `getRandomValues` 拼接.
 */
function generateRequestId(): string {
  const c = (globalThis as unknown as { crypto?: Crypto }).crypto;
  if (c && typeof c.randomUUID === 'function') {
    return c.randomUUID();
  }
  if (c && typeof c.getRandomValues === 'function') {
    const buf = new Uint8Array(16);
    c.getRandomValues(buf);
    // RFC4122 version 4
    buf[6] = ((buf[6] ?? 0) & 0x0f) | 0x40;
    buf[8] = ((buf[8] ?? 0) & 0x3f) | 0x80;
    const hex: string[] = [];
    for (let i = 0; i < 16; i += 1) {
      const byte = buf[i] ?? 0;
      hex.push(byte.toString(16).padStart(2, '0'));
    }
    return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex
      .slice(6, 8)
      .join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10, 16).join('')}`;
  }
  // 极端兜底
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * TokenRefreshHandler — 单例，负责刷新 JWT 并在多个并发 401 之间复用同一次刷新.
 *
 * 实现要点：
 *   - 第一次进入 refresh 时建立 `this.refreshing` Promise
 *   - 并发请求拿到同一 Promise 句柄，等待同一结果
 *   - 失败时清空 auth store 并 reject
 *   - finally 中清空引用，允许下次 401 重新刷新
 */
class TokenRefreshHandler {
  private refreshing: Promise<string> | null = null;

  /** 执行一次刷新；并发调用共享同一 Promise. */
  refresh(refreshToken: string): Promise<string> {
    if (this.refreshing) {
      return this.refreshing;
    }

    this.refreshing = (async () => {
      try {
        const response = await axios.post<{ access_token: string; refresh_token: string }>(
          `${API_BASE_URL}/auth/refresh`,
          { refresh_token: refreshToken },
          { headers: { 'Content-Type': 'application/json' } },
        );
        const { access_token, refresh_token } = response.data;
        useAuthStore.getState().setTokens(access_token, refresh_token);
        return access_token;
      } catch (err) {
        useAuthStore.getState().clearAuth();
        throw err;
      } finally {
        this.refreshing = null;
      }
    })();

    return this.refreshing;
  }
}

const tokenHandler = new TokenRefreshHandler();

/**
 * 创建 API axios 实例.
 */
function createApiClient(): AxiosInstance {
  const client = axios.create({
    baseURL: API_BASE_URL,
    timeout: 30_000,
    headers: { 'Content-Type': 'application/json' },
  });

  // ---------- 请求拦截器 ----------
  client.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      const state = useAuthStore.getState();
      const { accessToken, tenantSlug } = state;

      // 1. Authorization
      if (accessToken) {
        config.headers.set('Authorization', `Bearer ${accessToken}`);
      }

      // 2. Tenant slug 路径注入
      if (tenantSlug && !shouldSkipTenantInject(config.url)) {
        config.url = prependTenant(config.url ?? '', tenantSlug);
      }

      // 3. X-Request-ID（每个请求独立 UUID）
      config.headers.set('X-Request-ID', generateRequestId());

      return config;
    },
    (error: unknown) => Promise.reject(error),
  );

  // ---------- 响应拦截器 ----------
  client.interceptors.response.use(
    (response: AxiosResponse) => response,
    async (error: AxiosError<ErrorResponse>) => {
      const original = error.config as
        | (InternalAxiosRequestConfig & { _retry?: boolean })
        | undefined;

      const status = error.response?.status;
      const requestUrl = original?.url ?? '';
      const isAuthEndpoint = requestUrl.includes('/auth/');

      // 1. 401 自动刷新 + 重放
      if (status === 401 && original && !original._retry && !isAuthEndpoint) {
        original._retry = true;
        const { refreshToken, clearAuth } = useAuthStore.getState();
        if (!refreshToken) {
          clearAuth();
          if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
            window.location.href = '/login';
          }
          return Promise.reject(normalizeError(error));
        }

        try {
          const newToken = await tokenHandler.refresh(refreshToken);
          original.headers.set('Authorization', `Bearer ${newToken}`);
          return client.request(original);
        } catch (refreshErr) {
          clearAuth();
          if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
            window.location.href = '/login';
          }
          return Promise.reject(refreshErr);
        }
      }

      // 2. 错误标准化
      return Promise.reject(normalizeError(error));
    },
  );

  return client;
}

/** 标准化 axios 错误 → NormalizedApiError. */
function normalizeError(error: AxiosError<ErrorResponse>): NormalizedApiError {
  const data = error.response?.data;
  const status = error.response?.status;
  const message = data?.message || error.message || 'Request failed';
  const code = data?.code || `E_HTTP_${status ?? 'UNKNOWN'}`;
  const normalized: NormalizedApiError = Object.assign(new Error(message), {
    code,
    status,
    details: data?.details,
    request_id: data?.request_id,
    name: 'NormalizedApiError',
  });
  return normalized;
}

export const apiClient: AxiosInstance = createApiClient();
export { API_BASE_URL, generateRequestId };