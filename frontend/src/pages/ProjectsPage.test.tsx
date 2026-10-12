/**
 * ProjectsPage 组件测试 —— 项目列表渲染、新建项目弹窗提交、编辑弹窗禁用编码与空态。
 */

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ProjectsPage from './ProjectsPage'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { http, HttpResponse } from 'msw'

describe('项目管理页', () => {
  it('渲染项目列表编码、名称与状态标签', async () => {
    renderProviders(<ProjectsPage />)

    expect(await screen.findByText('演示项目')).toBeInTheDocument()
    expect(screen.getByText('DEMO')).toBeInTheDocument()
    expect(screen.getByText('MSW 默认项目')).toBeInTheDocument()
    expect(screen.getByText('active')).toBeInTheDocument()
  })

  it('打开新建项目弹窗并提交成功', async () => {
    const user = userEvent.setup()
    let posted: unknown = null
    server.use(
      http.post('/api/v1/projects', async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json(
          {
            id: 11,
            uid: 'p-new',
            parent_id: null,
            code: 'PRJ-001',
            name: '新项目',
            description: '',
            status: 'active',
            created_at: '2026-01-02T00:00:00Z',
            updated_at: '2026-01-02T00:00:00Z',
          },
          { status: 201 },
        )
      }),
    )

    renderProviders(<ProjectsPage />)

    await user.click(await screen.findByText('新建项目'))
    expect(await screen.findByPlaceholderText('如 PRJ-001')).toBeInTheDocument()

    await user.type(screen.getByLabelText('编码'), 'PRJ-001')
    await user.type(screen.getByLabelText('名称'), '新项目')
    await user.click(screen.getByText('确 定'))

    expect(await screen.findByText('项目创建成功')).toBeInTheDocument()
    expect(posted).toEqual({
      code: 'PRJ-001',
      name: '新项目',
      description: '',
      status: 'active',
      parent_id: null,
    })
  })

  it('行内编辑打开弹窗并禁用编码输入', async () => {
    const user = userEvent.setup()
    renderProviders(<ProjectsPage />)

    await user.click(await screen.findByText('编辑'))

    expect(await screen.findByText('编辑项目')).toBeInTheDocument()
    const codeInput = screen.getByLabelText('编码')
    expect(codeInput).toBeDisabled()
    expect(codeInput).toHaveValue('DEMO')
    expect(screen.getByLabelText('名称')).toHaveValue('演示项目')
  })

  it('项目列表为空时展示空态', async () => {
    server.use(http.get('/api/v1/projects', () => HttpResponse.json([])))

    renderProviders(<ProjectsPage />)

    expect(await screen.findByText('暂无项目')).toBeInTheDocument()
  })
})
