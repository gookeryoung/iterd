/**
 * MembersTab 组件测试 —— 成员列表渲染、添加成员弹窗与 403 禁用态。
 */

import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import MembersTab from './MembersTab'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { http, HttpResponse } from 'msw'
import type { Member } from '../types'

const members: Member[] = [
  { id: 1, project_id: 10, user_id: 1, role: 'owner', username: 'admin' },
  { id: 2, project_id: 10, user_id: 2, role: 'designer', username: 'designer' },
]

describe('成员 Tab', () => {
  it('渲染成员列表用户名与角色标签', async () => {
    server.use(http.get('/api/v1/projects/:id/members', () => HttpResponse.json(members)))

    renderProviders(<MembersTab projectId={10} />)

    expect(await screen.findByText('admin')).toBeInTheDocument()
    expect(screen.getByText('designer')).toBeInTheDocument()
    expect(screen.getByText('所有者')).toBeInTheDocument()
    expect(screen.getByText('设计者')).toBeInTheDocument()
  })

  it('打开添加成员弹窗并提交成功', async () => {
    const user = userEvent.setup()
    let posted: unknown = null
    server.use(
      http.get('/api/v1/projects/:id/members', () => HttpResponse.json(members)),
      http.put('/api/v1/projects/:id/members', async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json({ id: 3, project_id: 10, user_id: 2, role: 'reviewer', username: 'designer' })
      }),
    )

    renderProviders(<MembersTab projectId={10} />)

    await user.click(await screen.findByText('添加成员'))
    expect(await screen.findByText('已存在同用户记录时将更新其角色。')).toBeInTheDocument()

    // 选择用户后提交（user_id 无默认值，必填校验拦截空表单）
    await user.click(screen.getByRole('combobox', { name: '用户' }))
    await user.click(await screen.findByText('admin', { selector: '.ant-select-item-option-content' }))
    await user.click(screen.getByText('确 定'))

    expect(await screen.findByText('成员已保存')).toBeInTheDocument()
    expect(posted).toEqual({ user_id: 1, role: 'viewer' })
  })

  it('用户列表 403 时添加成员按钮禁用', async () => {
    server.use(
      http.get('/api/v1/projects/:id/members', () => HttpResponse.json([])),
      http.get('/api/v1/users', () => HttpResponse.json({}, { status: 403 })),
    )

    renderProviders(<MembersTab projectId={10} />)

    // 403 后组件切换为 Tooltip 包裹的禁用按钮，DOM 节点被替换，须在 waitFor 内重新查询
    await waitFor(() => expect(screen.getByText('添加成员').closest('button')).toBeDisabled())
    expect(await screen.findByText('暂无成员')).toBeInTheDocument()
  })
})
