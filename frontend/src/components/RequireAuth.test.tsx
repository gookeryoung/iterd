/**
 * RequireAuth 组件测试 —— 登录路由守卫两态：
 * 无 token → 重定向 /login（携带 from 路径）；有 token → 渲染子路由。
 */

import { describe, expect, it } from 'vitest'
import { Route, Routes, useLocation } from 'react-router-dom'
import { screen } from '@testing-library/react'
import RequireAuth from './RequireAuth'
import { renderProviders } from '../test/render'
import { setToken } from '../api/client'

/** 登录页探针 —— 渲染当前 location 供断言 from 携带与 state 内容 */
function LoginProbe() {
  const location = useLocation()
  return <span data-testid="login-page">登录页{JSON.stringify(location.state)}</span>
}

describe('RequireAuth 登录守卫', () => {
  it('无 token 时重定向到 /login 并携带 from 路径', () => {
    renderProviders(
      <Routes>
        <Route path="/login" element={<LoginProbe />} />
        <Route path="/rules" element={<RequireAuth />}>
          <Route index element={<div>受保护内容</div>} />
        </Route>
      </Routes>,
      { route: '/rules' },
    )

    expect(screen.getByTestId('login-page')).toHaveTextContent('{"from":"/rules"}')
    expect(screen.queryByText('受保护内容')).not.toBeInTheDocument()
  })

  it('有 token 时直接渲染子路由', () => {
    setToken('tok-authed')
    renderProviders(
      <Routes>
        <Route path="/login" element={<LoginProbe />} />
        <Route path="/rules" element={<RequireAuth />}>
          <Route index element={<div>受保护内容</div>} />
        </Route>
      </Routes>,
      { route: '/rules' },
    )

    expect(screen.getByText('受保护内容')).toBeInTheDocument()
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument()
  })
})
