/**
 * ProjectDetailPage 组件测试 —— 项目信息头、角色标签与 Tab 导航。
 */

import { describe, expect, it } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ProjectDetailPage from './ProjectDetailPage'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { http, HttpResponse } from 'msw'

function renderPage(): void {
  renderProviders(
    <Routes>
      <Route path="/projects/:id" element={<ProjectDetailPage />} />
    </Routes>,
    { route: '/projects/10' },
  )
}

describe('项目详情页', () => {
  it('渲染项目名称、编码与我的角色标签', async () => {
    renderPage()

    expect(await screen.findByText('演示项目')).toBeInTheDocument()
    expect(screen.getByText('DEMO')).toBeInTheDocument()
    expect(screen.getByText('我的角色：超级管理员')).toBeInTheDocument()
  })

  it('展示四个功能 Tab 并可切换到成员', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText('文档库')).toBeInTheDocument()
    expect(screen.getByText('迭代')).toBeInTheDocument()
    expect(screen.getByText('审查')).toBeInTheDocument()
    expect(screen.getByText('成员')).toBeInTheDocument()

    await user.click(screen.getByText('成员'))
    expect(await screen.findByText('添加成员')).toBeInTheDocument()
  })

  it('项目接口失败时展示错误提示', async () => {
    server.use(http.get('/api/v1/projects/:id', () => HttpResponse.json({}, { status: 500 })))

    renderPage()

    expect(await screen.findByText('项目加载失败')).toBeInTheDocument()
  })
})
