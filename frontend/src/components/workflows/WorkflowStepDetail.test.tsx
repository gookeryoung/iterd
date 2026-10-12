/**
 * WorkflowStepDetail 组件测试 —— 步骤头信息、日志列表与仅看错误过滤。
 */

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import WorkflowStepDetail from './WorkflowStepDetail'
import type { WorkflowJobStep } from '../../types'
import { renderProviders } from '../../test/render'

function buildStep(overrides: Partial<WorkflowJobStep> = {}): WorkflowJobStep {
  return {
    id: 1,
    job_id: 10,
    step_key: 'solve',
    name: '执行仿真',
    status: 'succeeded',
    conclusion: 'success',
    order_index: 1,
    logs: [
      { ts: 0.4, level: 'info', message: '加载模板与参数' },
      { ts: 2.1, level: 'error', message: '求解器返回超限' },
      { ts: 3.5, level: 'info', message: '阈值评估完成' },
    ],
    started_at: '2026-01-01T00:00:00Z',
    finished_at: '2026-01-01T00:00:04Z',
    ...overrides,
  }
}

describe('WorkflowStepDetail', () => {
  it('渲染步骤名称、step_key 与全部日志', () => {
    renderProviders(<WorkflowStepDetail step={buildStep()} />)

    expect(screen.getByText('执行仿真')).toBeInTheDocument()
    expect(screen.getByText('solve')).toBeInTheDocument()
    expect(screen.getByText('加载模板与参数')).toBeInTheDocument()
    expect(screen.getByText('求解器返回超限')).toBeInTheDocument()
    expect(screen.getByText('阈值评估完成')).toBeInTheDocument()
  })

  it('无日志时展示空态', () => {
    renderProviders(<WorkflowStepDetail step={buildStep({ logs: null })} />)

    expect(screen.getByText('暂无日志')).toBeInTheDocument()
  })

  it('存在错误日志时提供仅看错误过滤', async () => {
    const user = userEvent.setup()
    renderProviders(<WorkflowStepDetail step={buildStep()} />)

    await user.click(screen.getByRole('checkbox', { name: '仅看错误' }))

    expect(screen.getByText('求解器返回超限')).toBeInTheDocument()
    expect(screen.queryByText('加载模板与参数')).not.toBeInTheDocument()
    expect(screen.queryByText('阈值评估完成')).not.toBeInTheDocument()
  })

  it('无错误日志时不渲染仅看错误开关', () => {
    renderProviders(
      <WorkflowStepDetail
        step={buildStep({ logs: [{ ts: 0.2, level: 'info', message: '普通日志' }] })}
      />,
    )

    expect(screen.queryByRole('checkbox', { name: '仅看错误' })).not.toBeInTheDocument()
    expect(screen.getByText('普通日志')).toBeInTheDocument()
  })
})
