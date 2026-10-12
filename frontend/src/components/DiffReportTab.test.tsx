/**
 * DiffReportTab 组件测试 —— 差异分段渲染、报告生成展示、归档成功提示与 diff 失败错误态。
 */

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DiffReportTab from './DiffReportTab'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { http, HttpResponse } from 'msw'

const diffPayload = {
  iteration: { id: 1, number: 1, title: '演示迭代', status: 'active' },
  baseline: { id: 9, number: 1, title: '基线迭代', status: 'closed' },
  note: '自动选取前序已关闭迭代作为基线',
  artifacts: {
    added: [{ code: 'DWG-002', name: '新增图' }],
    removed: [{ code: 'DWG-001', name: '旧图' }],
    changed: [{ code: 'DWG-001', field: 'name', base: '旧图A', current: '旧图B' }],
  },
  bom: { added: [], removed: [], changed: [] },
  findings: {
    baseline: { error: 1, warning: 2, info: 0 },
    current: { error: 0, warning: 0, info: 0 },
  },
  sims: {
    baseline: { verdict: 'pass', failures: 0 },
    current: { verdict: 'fail', failures: 2 },
  },
  approvals: {
    baseline: { approved: 2, rejected: 0, pending_jobs: 0 },
    current: null,
  },
}

describe('迭代对比与审查报告 Tab', () => {
  it('渲染产物/BOM 差异分段与结论审批对比', async () => {
    server.use(http.get('/api/v1/iterations/1/diff', () => HttpResponse.json(diffPayload)))

    renderProviders(<DiffReportTab iterationId={1} projectId={10} />)

    expect(await screen.findByText('产物集合差异')).toBeInTheDocument()
    expect(screen.getByText('BOM 差异')).toBeInTheDocument()
    expect(screen.getByText('结论与审批对比')).toBeInTheDocument()
    expect(screen.getByText('DWG-002')).toBeInTheDocument()
    expect(screen.getByText('旧图（基线存在，当前已移除）')).toBeInTheDocument()
    expect(screen.getByText('name')).toBeInTheDocument()
    expect(screen.getByText('旧图A')).toBeInTheDocument()
    expect(screen.getByText('旧图B')).toBeInTheDocument()
    expect(screen.getByText('无差异（零件编码集合一致）')).toBeInTheDocument()
    expect(screen.getByText(/基线：迭代 1 基线迭代/)).toBeInTheDocument()
    expect(screen.getByText('自动选取前序已关闭迭代作为基线')).toBeInTheDocument()
    expect(screen.getByText(/error 1 \/ warning 2 \/ info 0/)).toBeInTheDocument()
    expect(screen.getByText(/超阈（2 项超阈）(\s|；|$)/)).toBeInTheDocument()
    expect(screen.getByText(/无审查运行/)).toBeInTheDocument()
  })

  it('生成报告后展示 Markdown 内容与下载按钮', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('/api/v1/iterations/1/diff', () => HttpResponse.json(diffPayload)),
      http.get('/api/v1/iterations/1/report', () =>
        HttpResponse.json({
          iteration_id: 1,
          generated_at: '2026-01-03T00:00:00Z',
          markdown: '# 审查报告\n\n全部通过。',
        }),
      ),
    )

    renderProviders(<DiffReportTab iterationId={1} projectId={10} />)

    await user.click(await screen.findByText('生成报告'))

    expect(await screen.findByText('生成时间：2026-01-03T00:00:00Z')).toBeInTheDocument()
    expect(screen.getByText(/全部通过/)).toBeInTheDocument()
    expect(screen.getByText('下载 Markdown')).toBeInTheDocument()
  })

  it('归档报告为产物并提示版本号', async () => {
    const user = userEvent.setup()
    let archived = false
    server.use(
      http.get('/api/v1/iterations/1/diff', () => HttpResponse.json(diffPayload)),
      http.post('/api/v1/iterations/1/report/archive', () => {
        archived = true
        return HttpResponse.json({ artifact_id: 5, artifact_code: 'RPT-001', version_no: 2 })
      }),
    )

    renderProviders(<DiffReportTab iterationId={1} projectId={10} />)

    await user.click(await screen.findByText('归档为产物'))

    expect(await screen.findByText('报告已归档为产物 RPT-001 v2')).toBeInTheDocument()
    expect(archived).toBe(true)
  })

  it('diff 接口失败时展示错误提示与报告空态', async () => {
    server.use(
      http.get('/api/v1/iterations/1/diff', () =>
        HttpResponse.json({ detail: '基线迭代不存在' }, { status: 500 }),
      ),
    )

    renderProviders(<DiffReportTab iterationId={1} projectId={10} />)

    expect(await screen.findByText('基线迭代不存在')).toBeInTheDocument()
    expect(
      screen.getByText(/点击「生成报告」按迭代聚合检查汇总/),
    ).toBeInTheDocument()
    expect(screen.queryByText('产物集合差异')).not.toBeInTheDocument()
  })
})
