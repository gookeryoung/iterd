/**
 * IterationsTab 组件测试 —— 迭代列表渲染、新建迭代提交、状态流转激活与编辑回填 PATCH。
 */

import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import IterationsTab from './IterationsTab'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { http, HttpResponse } from 'msw'
import type { Iteration } from '../types'

const iterations: Iteration[] = [
  {
    id: 1,
    uid: 'i-1',
    project_id: 10,
    number: 1,
    title: '方案设计',
    objective: '完成总装方案',
    start_date: '2026-01-01',
    end_date: '2026-01-15',
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 2,
    uid: 'i-2',
    project_id: 10,
    number: 2,
    title: '评审修改',
    objective: '',
    start_date: null,
    end_date: null,
    status: 'planned',
    created_at: '2026-01-02T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  },
]

function mockIterationsHandler(): void {
  server.use(http.get('/api/v1/projects/10/iterations', () => HttpResponse.json(iterations)))
}

describe('迭代 Tab', () => {
  it('渲染迭代列表标题、时间窗与状态标签', async () => {
    mockIterationsHandler()

    renderProviders(<IterationsTab projectId={10} />)

    expect(await screen.findByText('方案设计')).toBeInTheDocument()
    expect(screen.getByText('评审修改')).toBeInTheDocument()
    expect(screen.getByText('完成总装方案')).toBeInTheDocument()
    expect(screen.getByText('2026-01-01 ~ 2026-01-15')).toBeInTheDocument()
    expect(screen.getByText('- ~ -')).toBeInTheDocument()
    expect(screen.getByText('进行中')).toBeInTheDocument()
    expect(screen.getByText('已计划')).toBeInTheDocument()
  })

  it('新建迭代提交成功且日期为空', async () => {
    const user = userEvent.setup()
    let posted: unknown = null
    server.use(
      http.get('/api/v1/projects/10/iterations', () => HttpResponse.json(iterations)),
      http.post('/api/v1/projects/10/iterations', async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json(
          { ...iterations[1], id: 3, number: 3, title: '第三轮迭代', status: 'planned' },
          { status: 201 },
        )
      }),
    )

    renderProviders(<IterationsTab projectId={10} />)

    await user.click(await screen.findByText('新建迭代'))
    expect(await screen.findByText('编号自动自增，新迭代初始状态为「已计划」。')).toBeInTheDocument()

    await user.type(screen.getByLabelText('标题'), '第三轮迭代')
    await user.click(screen.getByText('确 定'))

    expect(await screen.findByText('迭代创建成功')).toBeInTheDocument()
    expect(posted).toEqual({
      title: '第三轮迭代',
      objective: '',
      start_date: null,
      end_date: null,
    })
  })

  it('激活已计划迭代调用状态流转接口', async () => {
    const user = userEvent.setup()
    let patched: unknown = null
    server.use(
      http.get('/api/v1/projects/10/iterations', () => HttpResponse.json(iterations)),
      http.patch('/api/v1/iterations/2', async ({ request }) => {
        patched = await request.json()
        return HttpResponse.json({ ...iterations[1], status: 'active' })
      }),
    )

    renderProviders(<IterationsTab projectId={10} />)

    await user.click(await screen.findByText('激活'))

    expect(await screen.findByText('迭代状态已更新为「进行中」')).toBeInTheDocument()
    expect(patched).toEqual({ status: 'active' })
  })

  it('编辑迭代回填表单并提交更新', async () => {
    const user = userEvent.setup()
    let patched: unknown = null
    server.use(
      http.get('/api/v1/projects/10/iterations', () => HttpResponse.json(iterations)),
      http.patch('/api/v1/iterations/1', async ({ request }) => {
        patched = await request.json()
        return HttpResponse.json({ ...iterations[0], title: '方案设计v2' })
      }),
    )

    renderProviders(<IterationsTab projectId={10} />)

    const firstRow = (await screen.findByText('方案设计')).closest('tr')
    expect(firstRow).not.toBeNull()
    await user.click(within(firstRow as HTMLElement).getByText('编辑'))

    expect(await screen.findByText('编辑迭代')).toBeInTheDocument()
    expect(screen.getByLabelText('标题')).toHaveValue('方案设计')
    expect(screen.getByLabelText('目标')).toHaveValue('完成总装方案')

    await user.clear(screen.getByLabelText('标题'))
    await user.type(screen.getByLabelText('标题'), '方案设计v2')
    await user.click(screen.getByText('确 定'))

    expect(await screen.findByText('迭代已更新')).toBeInTheDocument()
    expect(patched).toEqual({
      title: '方案设计v2',
      objective: '完成总装方案',
      start_date: '2026-01-01',
      end_date: '2026-01-15',
    })
  })
})
