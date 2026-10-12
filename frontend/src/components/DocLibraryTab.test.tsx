/**
 * DocLibraryTab 组件测试 —— 产物列表渲染、审查明细抽屉、仅看未通过过滤与图样树模式。
 */

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DocLibraryTab from './DocLibraryTab'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { http, HttpResponse } from 'msw'
import type { Artifact, ArtifactReviewStatus, ProjectLink } from '../types'

const artifacts: Artifact[] = [
  {
    id: 11,
    uid: 'a-11',
    project_id: 10,
    iteration_id: 1,
    code: 'DWG-001',
    name: '总装图',
    category: 'drawing',
    description: '',
    current_version_id: 5,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 12,
    uid: 'a-12',
    project_id: 10,
    iteration_id: 1,
    code: 'MDL-001',
    name: '整机模型',
    category: 'model',
    description: '',
    current_version_id: 6,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const reviewStatus: ArtifactReviewStatus[] = [
  {
    artifact_id: 11,
    code: 'DWG-001',
    name: '总装图',
    category: 'drawing',
    iteration_id: 1,
    current_version_id: 5,
    status: 'failed',
    check_run_id: 9,
    check_run_status: 'succeeded',
    last_checked_at: '2026-01-02T00:00:00Z',
    last_check_started_at: '2026-01-02T00:00:00Z',
    findings: [
      {
        id: 1,
        check_run_id: 9,
        artifact_version_id: 5,
        version_no: 1,
        rule_id: 100,
        rule_code: 'DRW-001',
        rule_name: '图层命名规范',
        severity: 'error',
        location: 'A1/1',
        message: '标题栏缺少版本号',
      },
    ],
  },
  {
    artifact_id: 12,
    code: 'MDL-001',
    name: '整机模型',
    category: 'model',
    iteration_id: 1,
    current_version_id: 6,
    status: 'passed',
    check_run_id: 9,
    check_run_status: 'succeeded',
    last_checked_at: null,
    last_check_started_at: null,
    findings: [],
  },
]

const links: ProjectLink[] = []

function mockDocHandlers(): void {
  server.use(
    http.get('/api/v1/artifacts', () => HttpResponse.json(artifacts)),
    http.get('/api/v1/projects/10/review-status', () => HttpResponse.json(reviewStatus)),
    http.get('/api/v1/projects/10/artifact-links', () => HttpResponse.json(links)),
  )
}

describe('文档库 Tab', () => {
  it('渲染产物列表编码、名称与审查状态标签', async () => {
    mockDocHandlers()

    renderProviders(<DocLibraryTab projectId={10} />)

    expect(await screen.findByText('DWG-001')).toBeInTheDocument()
    expect(screen.getByText('总装图')).toBeInTheDocument()
    expect(screen.getByText('MDL-001')).toBeInTheDocument()
    expect(screen.getByText('整机模型')).toBeInTheDocument()
    expect(screen.getByText('未通过')).toBeInTheDocument()
    expect(screen.getByText('通过')).toBeInTheDocument()
    expect(screen.getAllByText('#1').length).toBeGreaterThan(0)
  })

  it('点击审查明细打开抽屉并展示发现项', async () => {
    const user = userEvent.setup()
    mockDocHandlers()

    renderProviders(<DocLibraryTab projectId={10} />)

    await user.click((await screen.findAllByText('审查明细'))[0])

    expect(await screen.findByText('审查明细 - DWG-001 总装图')).toBeInTheDocument()
    expect(await screen.findByText('DRW-001 图层命名规范')).toBeInTheDocument()
    expect(screen.getByText('错误')).toBeInTheDocument()
    expect(screen.getByText('A1/1')).toBeInTheDocument()
    expect(screen.getByText('标题栏缺少版本号')).toBeInTheDocument()
    expect(screen.getByText('v1')).toBeInTheDocument()
    expect(screen.getByText('#9')).toBeInTheDocument()
  })

  it('开启仅看未通过后过滤掉已通过产物', async () => {
    const user = userEvent.setup()
    mockDocHandlers()

    renderProviders(<DocLibraryTab projectId={10} />)

    expect(await screen.findByText('MDL-001')).toBeInTheDocument()
    await user.click(screen.getByRole('switch'))

    expect(screen.getByText('DWG-001')).toBeInTheDocument()
    expect(screen.queryByText('MDL-001')).not.toBeInTheDocument()
  })

  it('切换到图纸类别进入树模式并归档未挂载图样', async () => {
    const user = userEvent.setup()
    mockDocHandlers()

    renderProviders(<DocLibraryTab projectId={10} />)

    expect(await screen.findByText('DWG-001')).toBeInTheDocument()

    // CheckableTag 文字在内层无类名 span 上，须先按文字定位再回溯外层可点击标签
    const drawingTag = screen
      .getAllByText('图纸')
      .map((el) => el.closest('.ant-tag-checkable'))
      .find((el): el is HTMLElement => el !== null)
    expect(drawingTag).not.toBeNull()
    await user.click(drawingTag as HTMLElement)

    expect(await screen.findByText('未挂载（无 part_of 关联）')).toBeInTheDocument()
    expect(screen.getByText('总装图')).toBeInTheDocument()
    expect(screen.queryByText('整机模型')).not.toBeInTheDocument()
  })
})
