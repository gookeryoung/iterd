/** 状态/枚举标签组件测试 —— 标签文案与语义色映射。 */

import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  CategoryTag,
  IterationStatusTag,
  ReviewStatusTag,
  SeverityTag,
} from './StatusTags'

describe('SeverityTag', () => {
  it('error / warning / info 渲染对应中文与语义色', () => {
    const { container: errorWrap } = render(<SeverityTag severity="error" />)
    expect(screen.getByText('错误')).toBeInTheDocument()
    expect(errorWrap.querySelector('.ant-tag-red')).not.toBeNull()

    const { container: warnWrap } = render(<SeverityTag severity="warning" />)
    expect(screen.getByText('警告')).toBeInTheDocument()
    expect(warnWrap.querySelector('.ant-tag-orange')).not.toBeNull()

    const { container: infoWrap } = render(<SeverityTag severity="info" />)
    expect(screen.getByText('提示')).toBeInTheDocument()
    expect(infoWrap.querySelector('.ant-tag-blue')).not.toBeNull()
  })
})

describe('IterationStatusTag', () => {
  it('planned / active / closed 渲染对应中文', () => {
    render(<IterationStatusTag status="planned" />)
    expect(screen.getByText('已计划')).toBeInTheDocument()
  })

  it('active 为绿色，closed 为灰色', () => {
    const { container: activeWrap } = render(<IterationStatusTag status="active" />)
    expect(activeWrap.querySelector('.ant-tag-green')).not.toBeNull()
    // antd 5 的 gray 不在预置色板内，走自定义颜色分支（ant-tag-has-color + 内联灰底）
    const { container: closedWrap } = render(<IterationStatusTag status="closed" />)
    const closedTag = closedWrap.querySelector('.ant-tag') as HTMLElement | null
    expect(closedTag).not.toBeNull()
    expect(closedTag).toHaveClass('ant-tag-has-color')
    expect(closedTag!.style.backgroundColor).toBe('gray')
  })
})

describe('CategoryTag', () => {
  it('渲染产物类别中文标签', () => {
    render(<CategoryTag category="drawing" />)
    expect(screen.getByText('图纸')).toBeInTheDocument()
  })

  it('未知类别回退展示原始编码', () => {
    render(<CategoryTag category={'unknown' as never} />)
    expect(screen.getByText('unknown')).toBeInTheDocument()
  })
})

describe('ReviewStatusTag', () => {
  it.each([
    ['passed', '通过', 'ant-tag-green'],
    ['failed', '未通过', 'ant-tag-red'],
    ['running', '运行中', 'ant-tag-blue'],
    ['unreviewed', '未审查', 'ant-tag-default'],
    ['stale', '已过期', 'ant-tag-orange'],
  ])('%s 渲染「%s」与 %s', (status, label, cls) => {
    const { container } = render(<ReviewStatusTag status={status as never} />)
    expect(screen.getByText(label)).toBeInTheDocument()
    expect(container.querySelector(`.${cls}`)).not.toBeNull()
  })
})
