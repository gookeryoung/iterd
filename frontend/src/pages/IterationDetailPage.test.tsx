/**
 * IterationDetailPage 组件测试 —— 迭代标题与信息、Tab 切换到审查流水线、加载失败与字段展示。
 */

import { describe, expect, it } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import IterationDetailPage from './IterationDetailPage'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { http, HttpResponse } from 'msw'
import type { Iteration } from '../types'

function renderPage(): void {
  renderProviders(
    <Routes>
      <Route path="/iterations/:id" element={<IterationDetailPage />} />
    </Routes>,
    { route: '/iterations/1' },
  )
}

describe('迭代详情页', () => {
  it('渲染迭代标题、状态标签与产物空态', async () => {
    renderPage()

    expect(await screen.findByText('迭代 1：演示迭代')).toBeInTheDocument()
    expect(screen.getByText('进行中')).toBeInTheDocument()
    expect(screen.getByText('返回项目').closest('a')).toHaveAttribute('href', '/projects/10')
    expect(screen.getByText('产物')).toBeInTheDocument()
    expect(screen.getByText('审查流水线')).toBeInTheDocument()
    // 默认产物 Tab：空列表空态
    expect(await screen.findByText('暂无产物')).toBeInTheDocument()
  })

  it('切换到审查流水线 Tab 展示空态', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('/api/v1/iterations/1/submissions', () => HttpResponse.json([])),
      http.get('/api/v1/iterations/1/workflow-runs', () => HttpResponse.json([])),
    )

    renderPage()
    await user.click(await screen.findByText('审查流水线'))

    expect(
      await screen.findByText('暂无审查运行：提交审查方案以触发流水线'),
    ).toBeInTheDocument()
    expect(screen.getByText('提交审查方案')).toBeInTheDocument()
  })

  it('迭代接口失败时展示错误提示', async () => {
    server.use(http.get('/api/v1/iterations/:id', () => HttpResponse.json({}, { status: 500 })))

    renderPage()

    expect(await screen.findByText('迭代加载失败')).toBeInTheDocument()
  })

  it('展示迭代目标与计划周期字段', async () => {
    const iteration: Iteration = {
      id: 1,
      uid: 'i-1',
      project_id: 10,
      number: 2,
      title: '传动方案迭代',
      objective: '完成传动方案设计',
      start_date: '2026-01-01',
      end_date: '2026-01-15',
      status: 'closed',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }
    server.use(http.get('/api/v1/iterations/:id', () => HttpResponse.json(iteration)))

    renderPage()

    expect(await screen.findByText('迭代 2：传动方案迭代')).toBeInTheDocument()
    expect(screen.getByText('已关闭')).toBeInTheDocument()
    expect(screen.getByText('完成传动方案设计')).toBeInTheDocument()
    expect(screen.getByText('2026-01-01 至 2026-01-15')).toBeInTheDocument()
  })
})
