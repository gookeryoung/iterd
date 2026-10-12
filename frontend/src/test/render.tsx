/**
 * 组件测试统一 render 工具 —— 对齐应用真实 Provider 结构：
 * QueryClientProvider（retry=false，用例间独立）+ ConfigProvider（antd zhCN）
 * + MemoryRouter（可注入初始路由）。
 */

import React from 'react'
import { render, renderHook, type RenderHookResult, type RenderOptions, type RenderResult } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { App as AntApp, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

export interface RenderProvidersOptions extends Omit<RenderOptions, 'wrapper'> {
  /** MemoryRouter 初始路由（如 '/' 或带 state 的 LocationDescription） */
  route?: string | { pathname: string; state?: unknown }
}

/** 创建用例独立的 QueryClient —— 关闭重试避免失败用例拖慢，gc 保留便于断言 */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false, staleTime: 0, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

/** 应用 Provider 栈（对齐 main.tsx：ConfigProvider + QueryClient + Router） */
function buildWrapper(route: RenderProvidersOptions['route'], queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <ConfigProvider locale={zhCN}>
          <AntApp>
            <MemoryRouter initialEntries={[route ?? '/']}>{children}</MemoryRouter>
          </AntApp>
        </ConfigProvider>
      </QueryClientProvider>
    )
  }
}

/** 统一 render —— 自动注入 QueryClient / antd 国际化 / 路由 */
export function renderProviders(
  ui: React.ReactElement,
  { route, ...renderOptions }: RenderProvidersOptions = {},
): RenderResult & { queryClient: QueryClient } {
  const queryClient = createTestQueryClient()
  const utils = render(ui, { wrapper: buildWrapper(route, queryClient), ...renderOptions })
  return { ...utils, queryClient }
}

/** 统一 renderHook —— Provider 栈与 renderProviders 一致 */
export function renderHookProviders<TResult>(
  callback: () => TResult,
  { route, ...renderOptions }: RenderProvidersOptions = {},
): RenderHookResult<TResult, RenderProvidersOptions> {
  const queryClient = createTestQueryClient()
  return renderHook(callback, { wrapper: buildWrapper(route, queryClient), ...renderOptions })
}
