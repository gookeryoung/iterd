/**
 * WorkflowRunView 组件测试 —— summary 条与默认作业详情、步骤切换、YAML 快照与重新运行。
 */

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import WorkflowRunView from './WorkflowRunView'
import { renderProviders } from '../../test/render'
import { server } from '../../test/msw'
import { http, HttpResponse } from 'msw'
import type { WorkflowJob, WorkflowJobStep, WorkflowRun } from '../../types'

const stepA: WorkflowJobStep = {
  id: 900,
  job_id: 501,
  step_key: 'prepare',
  name: '准备环境',
  status: 'succeeded',
  conclusion: 'success',
  order_index: 0,
  logs: [{ ts: 0.5, level: 'info', message: '环境就绪' }],
  started_at: '2026-01-01T00:10:00Z',
  finished_at: '2026-01-01T00:10:01Z',
}

const jobA: WorkflowJob = {
  id: 501,
  run_id: 41,
  job_key: 'a',
  name: '上游仿真',
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
  steps: [stepA],
}

const jobB: WorkflowJob = {
  ...jobA,
  id: 502,
  job_key: 'b',
  name: '下游仿真',
  needs: ['a'],
  order_index: 1,
  steps: [],
  logs: [],
}

const run: WorkflowRun = {
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
  submission_title: '传动方案第三版设计',
  jobs: [jobA, jobB],
}

describe('运行详情视图', () => {
  it('渲染 summary 条、作业树并默认选中首个作业', async () => {
    renderProviders(<WorkflowRunView run={run} />)

    expect(await screen.findByText('CONV-REVIEW #41')).toBeInTheDocument()
    expect(screen.getByText('方案提交')).toBeInTheDocument()
    expect(screen.getByText('传动方案第三版设计')).toBeInTheDocument()
    expect(screen.getByText('2 successful')).toBeInTheDocument()
    expect(screen.getByText('1 skipped')).toBeInTheDocument()
    expect(screen.getByText('作业与步骤')).toBeInTheDocument()
    expect(screen.getByText('下游仿真')).toBeInTheDocument()
    // 首个作业详情：作业名重复于树与详情面板
    expect(screen.getAllByText('上游仿真').length).toBeGreaterThan(0)
    expect(screen.getByText('梁强度校核')).toBeInTheDocument()
    expect(screen.getByText('检查完成')).toBeInTheDocument()
    // 详情面板步骤概要
    expect(screen.getByText('准备环境')).toBeInTheDocument()
  })

  it('点击步骤切换到步骤详情日志', async () => {
    const user = userEvent.setup()
    renderProviders(<WorkflowRunView run={run} />)

    // 详情面板步骤概要行可点击进入步骤日志
    await user.click(await screen.findByText('准备环境'))

    expect(await screen.findByText('prepare')).toBeInTheDocument()
    expect(await screen.findByText('环境就绪')).toBeInTheDocument()
  })

  it('点击 YAML 按钮展示运行定义快照', async () => {
    const user = userEvent.setup()
    renderProviders(<WorkflowRunView run={run} />)

    await user.click(await screen.findByText('YAML'))

    expect(await screen.findByText('运行定义快照（发起时固化）')).toBeInTheDocument()
    // YAML 行键匹配保留缩进，按 trim 后比较
    expect(screen.getByText((_, el) => el?.textContent?.trim() === 'name: 审查')).toBeInTheDocument()
    expect(
      screen.getByText((_, el) => el?.textContent?.trim() === 'uses: rules/check'),
    ).toBeInTheDocument()
  })

  it('重新运行成功后提示新运行编号', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('/api/v1/workflow-runs/41/rerun', () =>
        HttpResponse.json({ ...run, id: 42, jobs: [], status: 'pending', summary: null }),
      ),
    )

    renderProviders(<WorkflowRunView run={run} />)
    // antd 图标带 aria-label，按钮可访问名含图标前缀，改用文本定位
    await user.click(await screen.findByText('重新运行'))

    expect(await screen.findByText('已重新运行（新运行 #42）')).toBeInTheDocument()
  })
})
