/**
 * RulesPage 组件测试 —— 规则/规则集列表渲染、新建规则弹窗提交、启用开关与规则集成员抽屉。
 */

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import RulesPage from './RulesPage'
import { renderProviders } from '../test/render'
import { mockRule, mockRuleSet, server } from '../test/msw'
import { http, HttpResponse } from 'msw'

describe('规则库页', () => {
  it('渲染规则条目与规则集列表字段', async () => {
    renderProviders(<RulesPage />)

    expect(await screen.findByText('图层命名规范')).toBeInTheDocument()
    expect(screen.getByText('DRW-001')).toBeInTheDocument()
    expect(screen.getByText('制图')).toBeInTheDocument()
    expect(screen.getByText('警告')).toBeInTheDocument()
    expect(screen.getByText('演示规则集')).toBeInTheDocument()
    expect(screen.getByText('全局')).toBeInTheDocument()
  })

  it('打开新建规则弹窗选择分类与检查器后提交成功', async () => {
    const user = userEvent.setup()
    let posted: unknown = null
    server.use(
      http.post('/api/v1/rules', async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json({ ...mockRule, id: 101, code: 'RULE-D-001' }, { status: 201 })
      }),
    )

    renderProviders(<RulesPage />)

    await user.click(await screen.findByText('新建规则'))
    expect(await screen.findByPlaceholderText('如 RULE-D-001')).toBeInTheDocument()

    await user.type(screen.getByLabelText('编码'), 'RULE-D-001')
    await user.type(screen.getByLabelText('名称'), '图层前缀校验')
    await user.click(screen.getByRole('combobox', { name: '分类' }))
    await user.click(await screen.findByText('制图', { selector: '.ant-select-item-option-content' }))
    await user.click(screen.getByRole('combobox', { name: '检查器类型' }))
    await user.click(
      await screen.findByText('convention.filename（文件命名规范检查）', {
        selector: '.ant-select-item-option-content',
      }),
    )
    await user.click(screen.getByText('确 定'))

    expect(await screen.findByText('规则创建成功')).toBeInTheDocument()
    expect(posted).toEqual({
      code: 'RULE-D-001',
      name: '图层前缀校验',
      category: 'drafting',
      checker_type: 'convention.filename',
      params: null,
      severity_default: 'warning',
      description: '',
      enabled: true,
    })
  })

  it('切换启用开关调用更新接口并提示停用', async () => {
    const user = userEvent.setup()
    let patched: unknown = null
    server.use(
      http.patch('/api/v1/rules/100', async ({ request }) => {
        patched = await request.json()
        return HttpResponse.json({ ...mockRule, enabled: false })
      }),
    )

    renderProviders(<RulesPage />)

    await user.click(await screen.findByRole('switch'))

    expect(await screen.findByText('规则已停用')).toBeInTheDocument()
    expect(patched).toEqual({
      code: 'DRW-001',
      name: '图层命名规范',
      category: 'drafting',
      checker_type: 'convention.filename',
      params: null,
      severity_default: 'warning',
      enabled: false,
    })
  })

  it('打开规则集成员抽屉展示成员规则', async () => {
    server.use(
      http.get('/api/v1/rule-sets/200', () =>
        HttpResponse.json({ ...mockRuleSet, rule_ids: [100] }),
      ),
    )

    renderProviders(<RulesPage />)

    await userEvent.setup().click(await screen.findByText('成员规则'))

    expect(await screen.findByText('规则集成员 - 演示规则集')).toBeInTheDocument()
    expect(await screen.findByText('DRW-001 图层命名规范')).toBeInTheDocument()
  })
})
