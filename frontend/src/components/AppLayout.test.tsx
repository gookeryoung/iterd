/**
 * AppLayout 组件测试 —— 侧边栏导航、当前用户展示、路由选中态与退出登录。
 */

import { describe, expect, it } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AppLayout from './AppLayout'
import { renderProviders } from '../test/render'
import { TOKEN_KEY, setToken } from '../api/client'

/** 登录页探针 —— 验证退出登录后的跳转 */
function LoginProbe() {
  return <div data-testid="login-page">登录页</div>
}

function setup(route: string) {
  setToken('tok-layout')
  renderProviders(
    <Routes>
      <Route path="/login" element={<LoginProbe />} />
      <Route element={<AppLayout />}>
        <Route path="/" element={<div>项目内容</div>} />
        <Route path="/rules" element={<div>规则内容</div>} />
        <Route path="/workflows" element={<div>模板内容</div>} />
        <Route path="/audit" element={<div>审计内容</div>} />
      </Route>
    </Routes>,
    { route },
  )
}

describe('AppLayout 布局', () => {
  it('渲染五个主导航菜单项与品牌名', () => {
    setup('/')
    expect(screen.getByText('项目管理', { selector: '.ant-menu-title-content' })).toBeInTheDocument()
    expect(screen.getByText('规则库', { selector: '.ant-menu-title-content' })).toBeInTheDocument()
    expect(screen.getByText('模板管理', { selector: '.ant-menu-title-content' })).toBeInTheDocument()
    expect(screen.getByText('审批待办', { selector: '.ant-menu-title-content' })).toBeInTheDocument()
    expect(screen.getByText('审计日志', { selector: '.ant-menu-title-content' })).toBeInTheDocument()
    expect(screen.getByText('项目内容')).toBeInTheDocument()
  })

  it('Header 展示 /auth/me 返回的用户名', async () => {
    setup('/')
    // MSW 默认 handler 返回 admin
    expect(await screen.findByText('admin')).toBeInTheDocument()
  })

  it('/rules 路径下「规则库」菜单为选中态', async () => {
    setup('/rules')
    const item = await screen.findByText('规则库', { selector: '.ant-menu-title-content' })
    expect(item.closest('.ant-menu-item')).toHaveClass('ant-menu-item-selected')
    expect(screen.getByText('规则内容')).toBeInTheDocument()
  })
})

describe('AppLayout 退出登录', () => {
  it('下拉菜单退出：清除 token 并跳转 /login', async () => {
    const user = userEvent.setup()
    setup('/')

    // 用户名经 useQuery 异步加载，先等待渲染完成
    const username = await screen.findByText('admin')
    // 悬停头像区域展开下拉（antd Dropdown 默认 hover 触发）
    await user.hover(username)
    await user.click(await screen.findByText('退出登录'))

    expect(await screen.findByTestId('login-page')).toBeInTheDocument()
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(screen.queryByText('项目内容')).not.toBeInTheDocument()
  })
})
