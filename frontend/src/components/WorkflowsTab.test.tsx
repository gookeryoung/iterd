/**
 * WorkflowsTab 组件测试 —— 空态、提交分组运行列表与默认展开详情、提交方案弹窗、等待会签运行展示。
 */

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import WorkflowsTab from './WorkflowsTab'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { http, HttpResponse } from 'msw'
import type { IterationSubmission, WorkflowJob, WorkflowRun } from '../types'

const job: WorkflowJob = {
  id: 501,
  run_id: 41,
  job_key: 'beam-sim',
  name: '仿真验证',
  job_type: 'simulation',
  needs: null,
  config: null,
  status: 'succeeded',
  conclusion: 'success',
  check_run_id: null,
  sim_job_id: null,
  logs: [{ level: 'info', message: '检查完成' }],
  order_index: 0,
  started_at: '2026-01-01T00:10:00Z',
  finished_at: '2026-01-01T00:12:00Z',
  rule_set_name: '',
  template_code: 'BEAM-CHECK',
  template_name: '梁强度校核',
  solver_type: 'beam_static',
  artifact_code: 'JZ-001',
  version_no: 2,
  steps: [],
}

const run41: WorkflowRun = {
  id: 41,
  iteration_id: 1,
  workflow_id: 300,
  workflow_code: 'CONV-REVIEW',
  definition: 'name: 审查\njobs:\n  check:\n    uses: rules/check\n',
  status: 'succeeded',
  summary: {
    conclusion: 'success',
    jobs: { success: 2, failure: 0, skipped: 1 },
    findings: { error: 0, warning: 1, info: 0 },
    sims: { pass: 1, fail: 0 },
  },
  created_by: 1,
  submission_id: 11,
  trigger: 'submission',
  started_at: '2026-01-01T00:10:00Z',
  finished_at: '2026-01-01T00:12:00Z',
  created_at: '2026-01-01T00:10:00Z',
  task_id: null,
  submission_title: '',
  jobs: [job],
}

const submission: IterationSubmission = {
  id: 11,
  iteration_id: 1,
  title: '传动方案第三版设计',
  note: '本次变更要点',
  submitted_by: 1,
  created_at: '2026-01-01T00:10:00Z',
  runs: [run41],
}

describe('审查流水线 Tab', () => {
  it('无运行时展示空态与提交入口', async () => {
    server.use(
      http.get('/api/v1/iterations/1/submissions', () => HttpResponse.json([])),
      http.get('/api/v1/iterations/1/workflow-runs', () => HttpResponse.json([])),
    )

    renderProviders(<WorkflowsTab iterationId={1} />)

    expect(
      await screen.findByText('暂无审查运行：提交审查方案以触发流水线'),
    ).toBeInTheDocument()
    expect(screen.getByText('提交审查方案')).toBeInTheDocument()
  })

  it('渲染提交分组运行列表并默认展开最新运行详情', async () => {
    server.use(
      http.get('/api/v1/iterations/1/submissions', () => HttpResponse.json([submission])),
      http.get('/api/v1/iterations/1/workflow-runs', () => HttpResponse.json([])),
    )

    renderProviders(<WorkflowsTab iterationId={1} />)

    expect(await screen.findByText('传动方案第三版设计')).toBeInTheDocument()
    // 运行编号同时出现在行头与展开详情 summary 条
    expect((await screen.findAllByText('CONV-REVIEW #41')).length).toBeGreaterThan(0)
    // 作业摘要计数
    expect(screen.getByText(/2 successful \/ 0 failed \/ 1 skipped/)).toBeInTheDocument()
    // 默认展开最新运行 → 右侧渲染作业详情（作业名在树与详情面板重复出现）
    expect(screen.getByText('作业与步骤')).toBeInTheDocument()
    expect(screen.getAllByText('仿真验证').length).toBeGreaterThan(0)
    expect(screen.getByText('检查完成')).toBeInTheDocument()
    expect(screen.getByText(/本次变更要点/)).toBeInTheDocument()
  })

  it('提交审查方案弹窗提交成功', async () => {
    const user = userEvent.setup()
    let posted: unknown = null
    server.use(
      http.get('/api/v1/iterations/1/submissions', () => HttpResponse.json([])),
      http.get('/api/v1/iterations/1/workflow-runs', () => HttpResponse.json([])),
      http.post('/api/v1/iterations/1/submissions', async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json(
          { ...submission, id: 12, title: '联轴器方案初版', note: '', runs: [{ ...run41, id: 42, submission_id: 12 }] },
          { status: 202 },
        )
      }),
    )

    renderProviders(<WorkflowsTab iterationId={1} />)
    await user.click(await screen.findByText('提交审查方案'))

    // 弹窗标题与触发按钮同名，用输入框占位符确认弹窗已打开
    const titleInput = await screen.findByPlaceholderText('例如：传动方案第三版设计')
    await user.type(titleInput, '联轴器方案初版')
    await user.click(screen.getByText('确 定'))

    expect(await screen.findByText('方案已提交，触发 1 条审查运行')).toBeInTheDocument()
    expect(posted).toEqual({ title: '联轴器方案初版', note: '' })
  })

  it('等待会签的手动运行展示等待提示与触发徽标', async () => {
    const waitingRun: WorkflowRun = {
      ...run41,
      id: 42,
      submission_id: null,
      trigger: 'manual',
      status: 'waiting',
      summary: {
        status: 'waiting',
        awaiting_job_key: 'signoff',
        awaiting_job: '总装会签',
        awaiting_job_id: 503,
      },
      jobs: [],
    }
    server.use(
      http.get('/api/v1/iterations/1/submissions', () => HttpResponse.json([])),
      http.get('/api/v1/iterations/1/workflow-runs', () => HttpResponse.json([waitingRun])),
    )

    renderProviders(<WorkflowsTab iterationId={1} />)

    expect(await screen.findByText('手动运行')).toBeInTheDocument()
    expect(
      await screen.findByText('等待人工会签（待办中心签署后续跑）'),
    ).toBeInTheDocument()
    // 运行编号同时出现在行头与展开详情 summary 条
    expect((await screen.findAllByText('CONV-REVIEW #42')).length).toBeGreaterThan(0)
    expect(screen.getByText('手动发起')).toBeInTheDocument()
  })
})
