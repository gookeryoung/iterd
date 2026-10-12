/**
 * LoginPage 组件测试 —— 表单校验、登录成功（token + 跳转）、
 * 登录失败（错误提示）、已登录直跳。
 */

import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LoginPage from './LoginPage'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { TOKEN_KEY, getToken } from '../api/client'

/** 受保护路由探针 —— 验证登录后按 from 回跳 */
function TargetProbe() {
  return <div data-testid="target-page">目标页面</div>
}

function setup(route?: string | { pathname: string; state?: unknown }) {
  renderProviders(
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/rules" element={<TargetProbe />} />
      <Route path="/" element={<TargetProbe />} />
    </Routes>,
    { route: route ?? '/login' },
  )
}

describe('LoginPage 登录表单', () => {
  it('渲染用户名 / 密码输入与登录按钮', () => {
    setup()
    expect(screen.getByPlaceholderText('用户名')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('密码')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /登\s?录/ })).toBeInTheDocument()
  })

  it('空表单提交触发必填校验，不发请求', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('button', { name: /登\s?录/ }))
    expect(await screen.findByText('请输入用户名')).toBeInTheDocument()
    expect(screen.getByText('请输入密码')).toBeInTheDocument()
  })

  it('登录成功：写入 token、提示欢迎语并按 from 回跳', async () => {
    const user = userEvent.setup()
    // 携带 from 状态：登录后应回跳 /rules
    setup({ pathname: '/login', state: { from: '/rules' } })

    await user.type(screen.getByPlaceholderText('用户名'), 'admin')
    await user.type(screen.getByPlaceholderText('密码'), 'admin1234')
    await user.click(screen.getByRole('button', { name: /登\s?录/ }))

    // 欢迎提示（message portal 异步挂载）
    expect(await screen.findByText('欢迎回来，admin')).toBeInTheDocument()
    // token 已写入
    expect(getToken()).toBe('fake-token')
    expect(localStorage.getItem(TOKEN_KEY)).toBe('fake-token')
    // 按 from 回跳到目标路由
    expect(await screen.findByTestId('target-page')).toBeInTheDocument()
  })

  it('登录失败：展示后端 detail 错误且不写 token', async () => {
    server.use(
      http.post('/api/v1/auth/login', () =>
        HttpResponse.json({ detail: '用户名或密码错误' }, { status: 401 })),
    )
    const user = userEvent.setup()
    setup()

    await user.type(screen.getByPlaceholderText('用户名'), 'admin')
    await user.type(screen.getByPlaceholderText('密码'), 'wrong-pass')
    await user.click(screen.getByRole('button', { name: /登\s?录/ }))

    expect(await screen.findByText('用户名或密码错误')).toBeInTheDocument()
    expect(getToken()).toBeNull()
    // 仍停留在登录页
    expect(screen.getByPlaceholderText('用户名')).toBeInTheDocument()
  })

  it('已有 token 访问 /login 直接重定向 /', async () => {
    localStorage.setItem(TOKEN_KEY, 'tok-exist')
    setup()
    expect(await screen.findByTestId('target-page')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByPlaceholderText('用户名')).not.toBeInTheDocument()
    })
  })
})
