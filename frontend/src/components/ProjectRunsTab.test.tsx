/**
 * ProjectRunsTab 组件测试 —— 运行列表渲染、默认展开最新运行详情、空态与错误态。
 */

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import ProjectRunsTab from './ProjectRunsTab'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { http, HttpResponse } from 'msw'
import type { ProjectRunItem, WorkflowRun } from '../types'

const succeededRun: ProjectRunItem = {
  id: 42,
  iteration_id: 2,
  iteration_number: 2,
  iteration_title: '评审迭代',
  workflow_id: 300,
  workflow_code: 'CONV-REVIEW',
  status: 'succeeded',
  summary: {
    conclusion: 'success',
    jobs: { success: 1, failure: 0, skipped: 0 },
    findings: { error: 0, warning: 0, info: 0 },
    sims: { pass: 1, fail: 0 },
  },
  trigger: 'submission',
  started_at: '2026-01-02T01:00:00Z',
  finished_at: '2026-01-02T01:05:00Z',
  created_at: '2026-01-02T00:30:00Z',
}

const waitingRun: ProjectRunItem = {
  id: 41,
  iteration_id: 1,
  iteration_number: 1,
  iteration_title: '首轮迭代',
  workflow_id: 300,
  workflow_code: 'CONV-REVIEW',
  status: 'waiting',
  summary: null,
  trigger: 'manual',
  started_at: null,
  finished_at: null,
  created_at: '2026-01-01T00:30:00Z',
}

function buildRunDetail(id: number, jobName: string, jobType: 'rules' | 'simulation'): WorkflowRun {
  return {
    id,
    iteration_id: id - 40,
    workflow_id: 300,
    workflow_code: 'CONV-REVIEW',
    definition: 'jobs:\n  check:\n    uses: rules/check\n',
    status: id === 42 ? 'succeeded' : 'waiting',
    summary: succeededRun.summary,
    created_by: 1,
    submission_id: null,
    trigger: 'submission',
    started_at: '2026-01-02T01:00:00Z',
    finished_at: '2026-01-02T01:05:00Z',
    created_at: '2026-01-02T00:30:00Z',
    task_id: null,
    submission_title: '方案提交',
    jobs: [
      {
        id: id * 10,
        run_id: id,
        job_key: 'check',
        name: jobName,
        job_type: jobType,
        needs: [],
        config: null,
        status: 'succeeded',
        conclusion: 'success',
        check_run_id: null,
        sim_job_id: null,
        logs: [],
        order_index: 0,
        started_at: '2026-01-02T01:00:00Z',
        finished_at: '2026-01-02T01:04:00Z',
        rule_set_name: '演示规则集',
        template_code: '',
        template_name: '',
        solver_type: '',
        artifact_code: '',
        version_no: null,
        steps: [],
      },
    ],
  }
}

function mockRunsHandler(runs: ProjectRunItem[]): void {
  server.use(http.get('/api/v1/projects/10/workflow-runs', () => HttpResponse.json(runs)))
}

describe('审查运行 Tab', () => {
  it('渲染运行列表并默认展开最新运行详情', async () => {
    mockRunsHandler([succeededRun, waitingRun])
    server.use(http.get('/api/v1/workflow-runs/42', () => HttpResponse.json(buildRunDetail(42, '规则检查', 'rules'))))

    renderProviders(<ProjectRunsTab projectId={10} />)

    expect(await screen.findByText('CONV-REVIEW #42')).toBeInTheDocument()
    expect(screen.getByText('#2 评审迭代')).toBeInTheDocument()
    expect(screen.getByText('方案提交')).toBeInTheDocument()
    expect(await screen.findByText('作业与步骤')).toBeInTheDocument()
    // 作业名同时出现在作业树与详情面板，断言至少渲染一处
    expect((await screen.findAllByText('规则检查')).length).toBeGreaterThan(0)
  })

  it('渲染多条运行的触发方式与空时间占位', async () => {
    mockRunsHandler([succeededRun, waitingRun])
    server.use(http.get('/api/v1/workflow-runs/42', () => HttpResponse.json(buildRunDetail(42, '规则检查', 'rules'))))

    renderProviders(<ProjectRunsTab projectId={10} />)

    expect(await screen.findByText('#2 评审迭代')).toBeInTheDocument()
    expect(screen.getByText('#1 首轮迭代')).toBeInTheDocument()
    expect(screen.getByText('方案提交')).toBeInTheDocument()
    expect(screen.getByText('手动')).toBeInTheDocument()
    // waiting 运行无开始/结束时间，两列均显示占位符
    expect(screen.getAllByText('-').length).toBeGreaterThanOrEqual(2)
  })

  it('运行列表为空时展示空态', async () => {
    renderProviders(<ProjectRunsTab projectId={10} />)

    expect(await screen.findByText('暂无审查运行')).toBeInTheDocument()
  })

  it('运行接口失败时降级展示空态', async () => {
    server.use(http.get('/api/v1/projects/10/workflow-runs', () => HttpResponse.json({}, { status: 500 })))

    renderProviders(<ProjectRunsTab projectId={10} />)

    expect(await screen.findByText('暂无审查运行')).toBeInTheDocument()
  })
})
