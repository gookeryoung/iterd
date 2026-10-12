/**
 * SimTemplatesPanel 组件测试 —— 模板列表渲染、新建模板提交、编辑回填 PATCH 与空态。
 */

import { describe, expect, it } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SimTemplatesPanel from './SimTemplatesPanel'
import { renderProviders } from '../../test/render'
import { server } from '../../test/msw'
import { http, HttpResponse } from 'msw'
import type { SimTemplate, SolverInfo } from '../../types'

const templates: SimTemplate[] = [
  {
    id: 7,
    project_id: 10,
    code: 'BEAM-CHECK',
    name: '梁强度校核',
    solver_type: 'beam_static',
    params: null,
    thresholds: { max_stress: { max: 100 } },
    description: '',
    enabled: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const solvers: SolverInfo[] = [
  { solver_type: 'beam_static', description: '梁静力分析', inputs: [], metrics: [] },
  { solver_type: 'modal', description: '模态分析', inputs: [], metrics: [] },
]

const projectOptions = [{ value: 10, label: '演示项目' }]

function mockTemplateHandlers(): void {
  server.use(
    http.get('/api/v1/sim-templates', () => HttpResponse.json(templates)),
    http.get('/api/v1/solvers', () => HttpResponse.json(solvers)),
  )
}

describe('仿真模板面板', () => {
  it('渲染模板列表编码、求解器与阈值', async () => {
    mockTemplateHandlers()

    renderProviders(<SimTemplatesPanel projectOptions={projectOptions} />)

    expect(await screen.findByText('BEAM-CHECK')).toBeInTheDocument()
    expect(screen.getByText('梁强度校核')).toBeInTheDocument()
    expect(screen.getByText('beam_static')).toBeInTheDocument()
    expect(screen.getByText('演示项目')).toBeInTheDocument()
    expect(screen.getByText('{"max_stress":{"max":100}}')).toBeInTheDocument()
    // 「启用」同时出现在列头与状态标签
    expect(screen.getAllByText('启用').length).toBeGreaterThanOrEqual(1)
  })

  it('新建模板选择求解器后提交成功', async () => {
    const user = userEvent.setup()
    let posted: unknown = null
    server.use(
      http.get('/api/v1/sim-templates', () => HttpResponse.json(templates)),
      http.get('/api/v1/solvers', () => HttpResponse.json(solvers)),
      http.post('/api/v1/sim-templates', async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json(
          { ...templates[0], id: 8, code: 'NEW-TPL', name: '新模板' },
          { status: 201 },
        )
      }),
    )

    renderProviders(<SimTemplatesPanel projectOptions={projectOptions} />)

    await user.click(await screen.findByText('新建仿真模板'))
    expect(await screen.findByText('模板编码')).toBeInTheDocument()

    await user.type(screen.getByLabelText('模板编码'), 'NEW-TPL')
    await user.type(screen.getByLabelText('模板名称'), '新模板')
    await user.click(screen.getByRole('combobox', { name: '求解器' }))
    await user.click(
      await screen.findByText('beam_static（梁静力分析）', { selector: '.ant-select-item-option-content' }),
    )
    fireEvent.change(screen.getByLabelText('验收阈值（JSON，min/max）'), {
      target: { value: '{"max_stress":{"max":80}}' },
    })
    await user.click(screen.getByText('确 定'))

    expect(await screen.findByText('模板 NEW-TPL 已创建')).toBeInTheDocument()
    expect(posted).toEqual({
      code: 'NEW-TPL',
      name: '新模板',
      solver_type: 'beam_static',
      project_id: null,
      thresholds: { max_stress: { max: 80 } },
      description: '',
    })
  })

  it('编辑模板回填表单并提交部分更新', async () => {
    const user = userEvent.setup()
    let patched: unknown = null
    server.use(
      http.get('/api/v1/sim-templates', () => HttpResponse.json(templates)),
      http.get('/api/v1/solvers', () => HttpResponse.json(solvers)),
      http.patch('/api/v1/sim-templates/7', async ({ request }) => {
        patched = await request.json()
        return HttpResponse.json({ ...templates[0], name: '梁强度校核 Pro' })
      }),
    )

    renderProviders(<SimTemplatesPanel projectOptions={projectOptions} />)

    await user.click(await screen.findByText('编辑'))

    expect(await screen.findByText('编辑仿真模板（BEAM-CHECK）')).toBeInTheDocument()
    expect(screen.getByLabelText('模板编码')).toBeDisabled()
    expect(screen.getByLabelText('模板名称')).toHaveValue('梁强度校核')

    await user.clear(screen.getByLabelText('模板名称'))
    await user.type(screen.getByLabelText('模板名称'), '梁强度校核 Pro')
    await user.click(screen.getByText('确 定'))

    expect(await screen.findByText('模板 BEAM-CHECK 已更新')).toBeInTheDocument()
    expect(patched).toEqual({
      name: '梁强度校核 Pro',
      solver_type: 'beam_static',
      thresholds: { max_stress: { max: 100 } },
      description: '',
      enabled: true,
    })
  })

  it('模板列表为空时展示空态与引导按钮', async () => {
    server.use(
      http.get('/api/v1/sim-templates', () => HttpResponse.json([])),
      http.get('/api/v1/solvers', () => HttpResponse.json(solvers)),
    )

    renderProviders(<SimTemplatesPanel projectOptions={projectOptions} />)

    expect(await screen.findByText('暂无仿真模板')).toBeInTheDocument()
    expect(screen.getByText('新建第一个模板')).toBeInTheDocument()
  })
})
