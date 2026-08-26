/**
 * React Query 通用封装.
 *
 * - `useApiQuery`: 参数化 query。queryKey 自动附加 params，禁用条件取决于 params 是否为空.
 * - `useApiMutation`: mutation 默认 `retry: 0`，避免重复触发副作用.
 *
 * 配合 `main.tsx` 的全局 QueryClient 默认值（staleTime=30s, refetchOnWindowFocus=false,
 * retry=1），使用方通常无需再指定这些参数.
 */

import {
  useMutation,
  useQuery,
  type UseMutationOptions,
  type UseQueryOptions,
} from '@tanstack/react-query';

/**
 * 参数化查询 Hook.
 *
 * 类型说明：
 *   - TData: 返回数据类型
 *   - TParams: 入参类型（默认 void，用于无参查询）
 *
 * `enabled` 默认行为：当 params 为 undefined 或 null 时禁用查询（防止空参误触请求）.
 */
export function useApiQuery<TData, TParams = void>(
  queryKey: readonly unknown[],
  queryFn: (params: TParams) => Promise<TData>,
  params: TParams,
  options?: Omit<UseQueryOptions<TData, Error, TData>, 'queryKey' | 'queryFn'>,
) {
  return useQuery<TData, Error>({
    queryKey: [...queryKey, params],
    queryFn: () => queryFn(params),
    enabled: options?.enabled ?? (params !== undefined && params !== null),
    staleTime: 30_000,
    retry: 1,
    refetchOnWindowFocus: false,
    ...options,
  });
}

/**
 * Mutation Hook — 默认不重试.
 */
export function useApiMutation<TData, TVariables>(
  mutationFn: (variables: TVariables) => Promise<TData>,
  options?: UseMutationOptions<TData, Error, TVariables>,
) {
  return useMutation<TData, Error, TVariables>({
    mutationFn,
    retry: 0,
    ...options,
  });
}