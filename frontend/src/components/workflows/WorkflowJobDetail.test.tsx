/**
 * WorkflowJobDetail 组件测试 —— 规则作业发现项、仿真指标判定、审批会签面板与发现项加载失败。
 */

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import WorkflowJobDetail from './WorkflowJobDetail'
import { renderProviders } from '../../test/render'
import { server, mockPendingApproval } from '../../test/msw'
import { http, HttpResponse } from 'msw'
import type { Finding, SimResult, WorkflowJob } from '../../types'

function makeJob(overrides: Partial<WorkflowJob> = {}): WorkflowJob {
  return {
    id: 501,
    run_id: 41,
    job_key: 'check',
    name: '静态规则检查',
    job_type: 'rules',
    needs: null,
    config: null,
    status: 'succeeded',
    conclusion: 'success',
    check_run_id: 33,
    sim_job_id: null,
    logs: [{ level: 'info', message: '规则检查完成' }],
    order_index: 0,
    started_at: '2026-01-01T00:10:00Z',
    finished_at: '2026-01-01T00:12:00Z',
    rule_set_name: '结构规范集',
    template_code: '',
    template_name: '',
    solver_type: '',
    artifact_code: '',
    version_no: null,
    steps: [],
    ...overrides,
  }
}

const findings: Finding[] = [
  {
    id: 1,
    check_run_id: 33,
    artifact_version_id: 9,
    rule_item_id: 100,
    severity: 'error',
    location: 'A1/图层/标题栏',
    message: '图层名不符规范',
    rule_code: 'DRW-101',
    rule_name: '图层命名规范',
    artifact_code: 'JZ-001',
    artifact_name: '传动轴',
    version_no: 2,
  },
  {
    id: 2,
    check_run_id: 33,
    artifact_version_id: null,
    rule_item_id: 101,
    severity: 'warning',
    location: 'BOM/材质栏',
    message: '缺少技术要求说明',
    rule_code: 'DRW-110',
    rule_name: '技术要求',
    artifact_code: null,
    artifact_name: null,
    version_no: null,
  },
]

function useFindingsHandler(): void {
  server.use(
    http.get('/api/v1/check-runs/33/findings', ({ request }) => {
      const severity = new URL(request.url).searchParams.get('severity')
      return HttpResponse.json(severity === 'error' ? [findings[0]] : findings)
    }),
  )
}

describe('作业详情面板', () => {
  it('规则作业：展示绑定信息、error 标注卡与发现项明细表', async () => {
    useFindingsHandler()

    renderProviders(<WorkflowJobDetail job={makeJob()} />)

    expect(await screen.findByText('静态规则检查')).toBeInTheDocument()
    expect(screen.getByText('结构规范集')).toBeInTheDocument()
    expect(screen.getByText('#33')).toBeInTheDocument()
    // annotation 卡（error 级）
    expect(await screen.findByText('DRW-101 图层名不符规范')).toBeInTheDocument()
    expect(screen.getByText('JZ-001 v2 · A1/图层/标题栏')).toBeInTheDocument()
    // 发现项明细表
    expect(screen.getByText('错误')).toBeInTheDocument()
    expect(screen.getByText('警告')).toBeInTheDocument()
    expect(screen.getByText('DRW-101 图层命名规范')).toBeInTheDocument()
    expect(screen.getByText('JZ-001（v2）')).toBeInTheDocument()
    expect(screen.getByText('迭代级')).toBeInTheDocument()
  })

  it('仿真作业：展示指标判定表', async () => {
    const simResult: SimResult = {
      id: 1,
      sim_job_id: 77,
      metrics: { max_stress: 120.5 },
      verdict: 'pass',
      failures: 0,
      detail: [
        { key: 'max_stress', label: '最大应力', value: 120.5, unit: 'MPa', min: null, max: 200, passed: true },
      ],
      created_at: '2026-01-01T00:12:00Z',
    }
    server.use(http.get('/api/v1/sim-jobs/77/result', () => HttpResponse.json(simResult)))

    renderProviders(
      <WorkflowJobDetail
        job={makeJob({
          id: 502,
          name: '强度仿真',
          job_key: 'beam-sim',
          job_type: 'simulation',
          check_run_id: null,
          sim_job_id: 77,
          rule_set_name: '',
          template_code: 'BEAM-CHECK',
          template_name: '梁强度校核',
          solver_type: 'beam_static',
          artifact_code: 'JZ-001',
          version_no: 2,
          logs: [{ level: 'info', message: '求解完成' }],
        })}
      />,
    )

    expect(await screen.findByText('强度仿真')).toBeInTheDocument()
    expect(screen.getByText('梁强度校核')).toBeInTheDocument()
    expect(screen.getByText('BEAM-CHECK')).toBeInTheDocument()
    expect(screen.getByText('beam_static')).toBeInTheDocument()
    expect(await screen.findByText('仿真指标判定')).toBeInTheDocument()
    expect(screen.getByText('最大应力（max_stress）')).toBeInTheDocument()
    expect(screen.getByText('120.5 MPa')).toBeInTheDocument()
    expect(screen.getByText('通过')).toBeInTheDocument()
  })

  it('审批作业等待签署：展示会签进度、签署记录与签署入口', async () => {
    server.use(
      http.get('/api/v1/workflow-jobs/503/approvals', () =>
        HttpResponse.json([
          {
            id: 1,
            job_id: 503,
            run_id: 41,
            approver_id: 2,
            approver_name: 'reviewer-a',
            decision: 'approved',
            comment: '图纸符合规范',
            created_at: '2026-01-01T01:00:00Z',
          },
        ]),
      ),
      http.get('/api/v1/approvals/pending', () =>
        HttpResponse.json([{ ...mockPendingApproval, job_id: 503 }]),
      ),
    )

    renderProviders(
      <WorkflowJobDetail
        job={makeJob({
          id: 503,
          name: '总装会签',
          job_key: 'signoff',
          job_type: 'approval',
          status: 'waiting',
          conclusion: null,
          check_run_id: null,
          rule_set_name: '',
        })}
      />,
    )

    expect(await screen.findByText('总装会签')).toBeInTheDocument()
    expect(
      screen.getByText('会签审批作业：待指定签署人完成签署后，流水线自动续跑下游作业。'),
    ).toBeInTheDocument()
    expect(screen.getByText('会签审批')).toBeInTheDocument()
    expect(screen.getByText('等待签署')).toBeInTheDocument()
    // 进度环文本在签署记录与门槛数据到达后由默认值变为 1/2
    expect(await screen.findByText('1/2')).toBeInTheDocument()
    expect(
      screen.getByText((_, el) => el?.textContent === '会签门槛：需 2 人通过，当前 1 人'),
    ).toBeInTheDocument()
    expect(screen.getByText('reviewer-b')).toBeInTheDocument()
    expect(screen.getByText('图纸符合规范')).toBeInTheDocument()
    expect(screen.getByText('签署意见')).toBeInTheDocument()
  })

  it('发现项接口失败时展示错误提示', async () => {
    server.use(
      http.get('/api/v1/check-runs/33/findings', () =>
        HttpResponse.json({ detail: '数据库查询超时' }, { status: 500 }),
      ),
    )

    renderProviders(<WorkflowJobDetail job={makeJob()} />)

    // 错误文案同时命中外层容器与内层 span，用 findAllByText 断言存在
    expect(
      (
        await screen.findAllByText(
          (_, el) =>
            el?.textContent ===
            '发现项加载失败（检查运行 #33）：数据库查询超时，请刷新页面或检查服务端日志',
        )
      ).length,
    ).toBeGreaterThan(0)
    // 无 error 级发现项时不渲染标注卡
    expect(screen.queryByText(/DRW-101/)).not.toBeInTheDocument()
  })
})
