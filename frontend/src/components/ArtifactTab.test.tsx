/**
 * ArtifactTab 组件测试 —— 产物列表渲染、版本历史抽屉、新建产物提交与空态。
 */

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ArtifactTab from './ArtifactTab'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { http, HttpResponse } from 'msw'
import type { Artifact, ArtifactVersion } from '../types'

const artifacts: Artifact[] = [
  {
    id: 201,
    uid: 'a-201',
    project_id: 10,
    iteration_id: 1,
    code: 'JZ-001',
    name: '传动轴',
    category: 'drawing',
    description: '关键传动件图纸',
    current_version_id: 3,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 202,
    uid: 'a-202',
    project_id: 10,
    iteration_id: 1,
    code: 'MX-002',
    name: '装配模型',
    category: 'model',
    description: '',
    current_version_id: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const versions: ArtifactVersion[] = [
  {
    id: 301,
    uid: 'v-301',
    artifact_id: 201,
    version_no: 1,
    filename: 'JZ-001_revA.dwg',
    content_type: 'image/vnd.dwg',
    size: 2048,
    sha256: 'abcd1234ef567890abcdef1234567890abcdef1234567890abcdef1234567890',
    metadata_json: null,
    uploaded_by: 1,
    note: '首版',
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 302,
    uid: 'v-302',
    artifact_id: 201,
    version_no: 2,
    filename: 'JZ-001_revB.dwg',
    content_type: 'image/vnd.dwg',
    size: 4096,
    sha256: 'ef567890abcd1234abcdef1234567890abcdef1234567890abcdef1234567890',
    metadata_json: { 材料: 'Q235' },
    uploaded_by: 1,
    note: '',
    created_at: '2026-01-02T00:00:00Z',
  },
]

describe('产物 Tab', () => {
  it('渲染产物列表的编码、名称、类别与操作入口', async () => {
    server.use(http.get('/api/v1/artifacts', () => HttpResponse.json(artifacts)))

    renderProviders(<ArtifactTab iterationId={1} />)

    expect(await screen.findByText('JZ-001')).toBeInTheDocument()
    expect(screen.getByText('传动轴')).toBeInTheDocument()
    expect(screen.getByText('MX-002')).toBeInTheDocument()
    expect(screen.getByText('装配模型')).toBeInTheDocument()
    expect(screen.getByText('图纸')).toBeInTheDocument()
    expect(screen.getByText('模型')).toBeInTheDocument()
    // 当前版本：有版本显示 #id，无版本显示「无」
    expect(screen.getByText('#3')).toBeInTheDocument()
    expect(screen.getByText('无')).toBeInTheDocument()
    // 每行操作入口齐全
    expect(screen.getAllByText('上传新版本')).toHaveLength(2)
    expect(screen.getAllByText('版本历史')).toHaveLength(2)
    expect(screen.getAllByText('关联')).toHaveLength(2)
    expect(screen.getAllByText('编辑')).toHaveLength(2)
    expect(screen.getAllByText('删除')).toHaveLength(2)
  })

  it('打开版本历史抽屉展示版本列表', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('/api/v1/artifacts', () => HttpResponse.json(artifacts)),
      http.get('/api/v1/artifacts/201/versions', () => HttpResponse.json(versions)),
    )

    renderProviders(<ArtifactTab iterationId={1} />)
    await user.click((await screen.findAllByText('版本历史'))[0])

    expect(await screen.findByText('版本历史 - 传动轴')).toBeInTheDocument()
    expect(await screen.findByText('JZ-001_revA.dwg')).toBeInTheDocument()
    expect(screen.getByText('JZ-001_revB.dwg')).toBeInTheDocument()
    expect(screen.getByText('v1')).toBeInTheDocument()
    expect(screen.getByText('v2')).toBeInTheDocument()
    // 大小与 SHA256 前 8 位
    expect(screen.getByText('2.0 KB')).toBeInTheDocument()
    expect(screen.getByText('abcd1234')).toBeInTheDocument()
    expect(screen.getByText('首版')).toBeInTheDocument()
  })

  it('打开新建产物弹窗提交成功', async () => {
    const user = userEvent.setup()
    let posted: unknown = null
    server.use(
      http.get('/api/v1/artifacts', () => HttpResponse.json(artifacts)),
      http.post('/api/v1/artifacts', async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json(
          {
            id: 203,
            uid: 'a-203',
            project_id: 10,
            iteration_id: 1,
            code: 'ART-101',
            name: '联轴器',
            category: 'drawing',
            description: '',
            current_version_id: null,
            created_at: '2026-01-03T00:00:00Z',
            updated_at: '2026-01-03T00:00:00Z',
          },
          { status: 201 },
        )
      }),
    )

    renderProviders(<ArtifactTab iterationId={1} />)
    await user.click(await screen.findByText('新建产物'))

    // 弹窗标题与触发按钮同名，用占位符确认弹窗已打开
    expect(await screen.findByPlaceholderText('如 ART-001')).toBeInTheDocument()
    await user.type(screen.getByPlaceholderText('如 ART-001'), 'ART-101')
    await user.type(screen.getByPlaceholderText('产物名称'), '联轴器')
    await user.click(screen.getByRole('combobox'))
    await user.click(await screen.findByText('图纸', { selector: '.ant-select-item-option-content' }))
    await user.click(screen.getByText('确 定'))

    expect(await screen.findByText('产物创建成功')).toBeInTheDocument()
    expect(posted).toEqual({ code: 'ART-101', name: '联轴器', category: 'drawing' })
  })

  it('无产物时展示空态', async () => {
    renderProviders(<ArtifactTab iterationId={1} />)

    expect(await screen.findByText('暂无产物')).toBeInTheDocument()
  })
})
