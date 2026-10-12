/**
 * PendingApprovalsPage 组件测试 —— 待审批列表渲染、签署弹窗提交流程与不可签场景。
 */

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PendingApprovalsPage from './PendingApprovalsPage'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { http, HttpResponse } from 'msw'

describe('审批待办中心', () => {
  it('渲染待审批作业卡片与会签进度', async () => {
    renderProviders(<PendingApprovalsPage />)

    expect(await screen.findByText('CONV-REVIEW · 总装会签')).toBeInTheDocument()
    expect(screen.getByText('signoff')).toBeInTheDocument()
    expect(screen.getByText((_, el) => el?.textContent === '会签门槛：需 2 人通过，当前 1 人')).toBeInTheDocument()
    expect(screen.getAllByText('reviewer-a').length).toBeGreaterThan(0)
    expect(screen.getByText('图纸符合规范')).toBeInTheDocument()
    expect(screen.getByText('签署意见')).toBeInTheDocument()
  })

  it('点击签署：打开弹窗提交通过意见并成功', async () => {
    const user = userEvent.setup()
    let posted: unknown = null
    server.use(
      http.post('/api/v1/workflow-jobs/:id/approvals', async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json(
          {
            id: 9,
            job_id: 501,
            run_id: 41,
            approver_id: 1,
            approver_name: 'admin',
            decision: 'approved',
            comment: '同意',
            created_at: '2026-01-01T02:00:00Z',
          },
          { status: 201 },
        )
      }),
    )

    renderProviders(<PendingApprovalsPage />)
    await user.click(await screen.findByText('签署意见'))

    // 弹窗：默认通过，填写意见后提交
    const modal = await screen.findByText('签署审批意见')
    expect(modal).toBeInTheDocument()
    await user.click(screen.getByText('提交签署'))

    expect(await screen.findByText('签署成功；若达成会签条件，流水线将自动续跑')).toBeInTheDocument()
    expect(posted).toEqual({ decision: 'approved', comment: '' })
  })

  it('弹窗内选择驳回：展示驳回风险提示并提交驳回决定', async () => {
    const user = userEvent.setup()
    let posted: unknown = null
    server.use(
      http.post('/api/v1/workflow-jobs/:id/approvals', async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json(
          {
            id: 10,
            job_id: 501,
            run_id: 41,
            approver_id: 1,
            approver_name: 'admin',
            decision: 'rejected',
            comment: '强度不足',
            created_at: '2026-01-01T03:00:00Z',
          },
          { status: 201 },
        )
      }),
    )

    renderProviders(<PendingApprovalsPage />)
    await user.click(await screen.findByText('签署意见'))

    await user.click(screen.getByText('驳回'))
    expect(screen.getByText('驳回将立即终止该流水线：后续作业全部跳过，运行置为失败。')).toBeInTheDocument()

    await user.type(screen.getByPlaceholderText('补充审批说明（可选）'), '强度不足')
    await user.click(screen.getByText('提交签署'))

    expect(await screen.findByText('已驳回；流水线下游作业将被终止')).toBeInTheDocument()
    expect(posted).toEqual({ decision: 'rejected', comment: '强度不足' })
  })

  it('不可签署时展示提示且无签署按钮', async () => {
    server.use(
      http.get('/api/v1/approvals/pending', () =>
        HttpResponse.json([
          {
            job_id: 502,
            run_id: 42,
            workflow_code: 'CONV-REVIEW',
            iteration_id: 1,
            project_id: 10,
            job_key: 'signoff',
            job_name: '总装会签',
            approvers: ['someone-else'],
            min_count: 1,
            approved_count: 0,
            approvals: [],
            can_approve: false,
            created_at: '2026-01-01T00:30:00Z',
          },
        ]),
      ),
    )

    renderProviders(<PendingApprovalsPage />)

    expect(await screen.findByText('当前账号不在签署范围内，仅可查看会签进度。')).toBeInTheDocument()
    expect(screen.queryByText('签署意见')).not.toBeInTheDocument()
  })

  it('空列表展示空态', async () => {
    server.use(
      http.get('/api/v1/approvals/pending', () => HttpResponse.json([])),
    )

    renderProviders(<PendingApprovalsPage />)

    expect(await screen.findByText('暂无待审批会签作业')).toBeInTheDocument()
  })
})
