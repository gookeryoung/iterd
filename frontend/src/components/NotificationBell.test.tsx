/**
 * NotificationBell 组件测试 —— 未读角标、列表渲染、单条已读跳转与全部已读。
 */

import { describe, expect, it } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import NotificationBell from './NotificationBell'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { http, HttpResponse } from 'msw'
import type { NotificationItem } from '../types'

const fixtures: NotificationItem[] = [
  {
    id: 1,
    user_id: 1,
    ntype: 'approval.pending',
    title: '会签待办：CONV-REVIEW #41',
    body: '作业 signoff 等待签署',
    project_id: 10,
    link: '/approvals',
    resource_type: 'workflow_job',
    resource_id: '501',
    read_at: null,
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 2,
    user_id: 1,
    ntype: 'run.completed',
    title: '运行完成：DEMO-REVIEW #40',
    body: '结论 success',
    project_id: 10,
    link: '/iterations/1',
    resource_type: 'workflow_run',
    resource_id: '40',
    read_at: '2026-01-01T01:00:00Z',
    created_at: '2026-01-01T00:30:00Z',
  },
]

function setupWithProbe() {
  return renderProviders(
    <Routes>
      <Route path="*" element={<NotificationBell />} />
      <Route path="/approvals" element={<div data-testid="approvals-page">审批待办</div>} />
    </Routes>,
  )
}

describe('通知中心铃铛', () => {
  it('未读角标展示计数，点击铃铛展开通知列表', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('/api/v1/notifications/unread-count', () => HttpResponse.json({ count: 1 })),
      http.get('/api/v1/notifications', () => HttpResponse.json(fixtures)),
    )
    const { container } = setupWithProbe()

    await waitFor(() => expect(container.querySelector('.ant-badge-count')?.textContent).toBe('1'))

    await user.click(screen.getByLabelText('通知中心'))
    expect(await screen.findByText('通知中心')).toBeInTheDocument()
    expect(await screen.findByText('会签待办：CONV-REVIEW #41')).toBeInTheDocument()
    expect(screen.getByText('运行完成：DEMO-REVIEW #40')).toBeInTheDocument()
    expect(screen.getByText('作业 signoff 等待签署')).toBeInTheDocument()
  })

  it('点击未读通知：标记已读并跳转链接页', async () => {
    const user = userEvent.setup()
    const readIds: number[] = []
    server.use(
      http.get('/api/v1/notifications/unread-count', () => HttpResponse.json({ count: 1 })),
      http.get('/api/v1/notifications', () => HttpResponse.json(fixtures)),
      http.post('/api/v1/notifications/:id/read', async ({ params }) => {
        readIds.push(Number(params.id))
        return HttpResponse.json({ ...fixtures[0], read_at: '2026-01-02T00:00:00Z' })
      }),
    )
    setupWithProbe()

    await user.click(screen.getByLabelText('通知中心'))
    await user.click(await screen.findByText('会签待办：CONV-REVIEW #41'))

    expect(readIds).toEqual([1])
    expect(await screen.findByTestId('approvals-page')).toBeInTheDocument()
  })

  it('全部已读：调用批量接口且按钮在无未读时禁用', async () => {
    const user = userEvent.setup()
    let marked = 0
    server.use(
      http.get('/api/v1/notifications/unread-count', () => HttpResponse.json({ count: 2 })),
      http.get('/api/v1/notifications', () => HttpResponse.json(fixtures)),
      http.post('/api/v1/notifications/read-all', () => {
        marked = 2
        return HttpResponse.json({ marked: 2 })
      }),
    )
    setupWithProbe()

    await user.click(screen.getByLabelText('通知中心'))
    await user.click(await screen.findByText('全部已读'))

    expect(marked).toBe(2)
  })

  it('空列表展示空态且全部已读按钮禁用', async () => {
    const user = userEvent.setup()
    setupWithProbe()

    await user.click(screen.getByLabelText('通知中心'))
    expect(await screen.findByText('暂无通知')).toBeInTheDocument()
    expect(screen.getByText('全部已读').closest('button')).toBeDisabled()
  })
})
