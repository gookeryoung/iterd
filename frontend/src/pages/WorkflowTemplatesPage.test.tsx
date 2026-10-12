/**
 * WorkflowTemplatesPage 组件测试 —— 审查模板列表、YAML 查看弹窗、新建模板抽屉与仿真模板 Tab。
 */

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import WorkflowTemplatesPage from './WorkflowTemplatesPage'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { http, HttpResponse } from 'msw'
import type { SimTemplate, SolverInfo } from '../types'

const simTemplate: SimTemplate = {
  id: 400,
  project_id: null,
  code: 'BEAM-CHECK',
  name: '梁强度校核',
  solver_type: 'beam_static',
  params: null,
  thresholds: { max_stress: { max: 100 } },
  description: '',
  enabled: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const solver: SolverInfo = {
  solver_type: 'beam_static',
  description: '梁静力求解',
  inputs: [],
  metrics: [],
}

describe('模板管理页', () => {
  it('渲染审查模板列表的编码、名称、范围与作业数', async () => {
    renderProviders(<WorkflowTemplatesPage />)

    expect(await screen.findByText('模板管理')).toBeInTheDocument()
    expect(await screen.findByText('DEMO-REVIEW')).toBeInTheDocument()
    expect(screen.getByText('演示审查流水线')).toBeInTheDocument()
    expect(screen.getByText('全局')).toBeInTheDocument()
    expect(screen.getByText('1 个')).toBeInTheDocument()
    // 表头「启用」与行内启用标签同时存在
    expect(screen.getAllByText('启用').length).toBeGreaterThan(0)
    expect(screen.getByText('审查模板')).toBeInTheDocument()
    expect(screen.getByText('仿真模板')).toBeInTheDocument()
  })

  it('点击 YAML 打开查看弹窗展示定义内容', async () => {
    const user = userEvent.setup()
    renderProviders(<WorkflowTemplatesPage />)

    await user.click(await screen.findByText('YAML'))

    expect(await screen.findByText('DEMO-REVIEW 演示审查流水线')).toBeInTheDocument()
    // YAML 行键匹配保留缩进，按 trim 后比较
    expect(screen.getByText((_, el) => el?.textContent?.trim() === 'jobs:')).toBeInTheDocument()
    expect(
      screen.getByText((_, el) => el?.textContent?.trim() === 'uses: rules/check'),
    ).toBeInTheDocument()
  })

  it('打开新建模板抽屉展示默认 YAML 与预览', async () => {
    const user = userEvent.setup()
    renderProviders(<WorkflowTemplatesPage />)

    await user.click(await screen.findByText('新建模板'))

    expect(await screen.findByText('新建审查模板')).toBeInTheDocument()
    expect(await screen.findByText('预览：详细设计审查')).toBeInTheDocument()
    expect(screen.getByText('保存（校验 YAML）')).toBeInTheDocument()
  })

  it('切换到仿真模板 Tab 展示仿真模板列表', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('/api/v1/sim-templates', () => HttpResponse.json([simTemplate])),
      http.get('/api/v1/solvers', () => HttpResponse.json([solver])),
    )

    renderProviders(<WorkflowTemplatesPage />)
    await user.click(screen.getByText('仿真模板'))

    expect(await screen.findByText('BEAM-CHECK')).toBeInTheDocument()
    expect(screen.getByText('梁强度校核')).toBeInTheDocument()
    expect(screen.getByText('beam_static')).toBeInTheDocument()
    expect(screen.getByText('{"max_stress":{"max":100}}')).toBeInTheDocument()
    expect(screen.getByText('新建仿真模板')).toBeInTheDocument()
  })
})
