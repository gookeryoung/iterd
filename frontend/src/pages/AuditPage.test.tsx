/**
 * AuditPage 组件测试 —— 审计日志表格渲染与空态。
 */

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import AuditPage from './AuditPage'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { http, HttpResponse } from 'msw'

describe('审计日志页', () => {
  it('渲染标题与日志行字段', async () => {
    renderProviders(<AuditPage />)

    expect(await screen.findByText('审计日志')).toBeInTheDocument()
    expect(await screen.findByText('login')).toBeInTheDocument()
    expect(screen.getByText('admin')).toBeInTheDocument()
    expect(screen.getByText('auth')).toBeInTheDocument()
    expect(screen.getByText('127.0.0.1')).toBeInTheDocument()
  })

  it('多条日志全部渲染', async () => {
    server.use(
      http.get('/api/v1/audit-logs', () =>
        HttpResponse.json([
          {
            id: 1,
            actor_id: 1,
            actor_name: 'admin',
            action: 'project.create',
            resource_type: 'project',
            resource_id: '10',
            before: null,
            after: null,
            ip: '10.0.0.8',
            created_at: '2026-01-01T00:00:00Z',
          },
          {
            id: 2,
            actor_id: 2,
            actor_name: 'designer',
            action: 'artifact.upload',
            resource_type: 'artifact',
            resource_id: '3',
            before: null,
            after: null,
            ip: '10.0.0.9',
            created_at: '2026-01-01T01:00:00Z',
          },
        ]),
      ),
    )

    renderProviders(<AuditPage />)

    expect(await screen.findByText('project.create')).toBeInTheDocument()
    expect(screen.getByText('artifact.upload')).toBeInTheDocument()
    expect(screen.getByText('designer')).toBeInTheDocument()
  })

  it('无日志时展示空态', async () => {
    server.use(http.get('/api/v1/audit-logs', () => HttpResponse.json([])))

    renderProviders(<AuditPage />)

    expect(await screen.findByText('暂无审计日志')).toBeInTheDocument()
  })
})
