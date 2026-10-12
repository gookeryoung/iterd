/** 运行状态图标组件测试 —— 状态→图标映射、徽标文案、旋转样式注入。 */

import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  JobStatusIcon,
  JobTypeBadge,
  RunningIcon,
  RunStatusIcon,
  TriggerBadge,
} from './RunStatusIcon'

function aria(name: string) {
  // SVG aria-label 断言：同一页面多次渲染时按图标语义定位
  return screen.getByLabelText(name)
}

describe('JobStatusIcon 状态映射', () => {
  it('conclusion=skipped → 跳过图标', () => {
    render(<JobStatusIcon status="pending" conclusion="skipped" />)
    expect(aria('已跳过')).toBeInTheDocument()
  })

  it('status=skipped → 跳过图标（无 conclusion）', () => {
    render(<JobStatusIcon status="skipped" conclusion={null} />)
    expect(aria('已跳过')).toBeInTheDocument()
  })

  it('conclusion=success → 成功图标', () => {
    render(<JobStatusIcon status="succeeded" conclusion="success" />)
    expect(aria('成功')).toBeInTheDocument()
  })

  it('conclusion=failure / status=failed → 失败图标', () => {
    const { unmount } = render(<JobStatusIcon status="succeeded" conclusion="failure" />)
    expect(aria('失败')).toBeInTheDocument()
    unmount()
    render(<JobStatusIcon status="failed" conclusion={null} />)
    expect(aria('失败')).toBeInTheDocument()
  })

  it('status=running → 进行中图标', () => {
    render(<JobStatusIcon status="running" conclusion={null} />)
    expect(aria('进行中')).toBeInTheDocument()
  })

  it('pending 兜底 → 排队图标', () => {
    render(<JobStatusIcon status="pending" conclusion={null} />)
    expect(aria('排队中')).toBeInTheDocument()
  })
})

describe('RunStatusIcon 运行级映射', () => {
  it('running → 进行中；pending → 排队', () => {
    const { unmount } = render(<RunStatusIcon status="running" summary={null} />)
    expect(aria('进行中')).toBeInTheDocument()
    unmount()
    render(<RunStatusIcon status="pending" summary={null} />)
    expect(aria('排队中')).toBeInTheDocument()
  })

  it('终态 + summary.conclusion=success → 成功', () => {
    render(<RunStatusIcon status="succeeded" summary={{ conclusion: 'success' }} />)
    expect(aria('成功')).toBeInTheDocument()
  })

  it('终态 + 无 summary / failure → 失败', () => {
    const { unmount } = render(<RunStatusIcon status="succeeded" summary={null} />)
    expect(aria('失败')).toBeInTheDocument()
    unmount()
    render(<RunStatusIcon status="succeeded" summary={{ conclusion: 'failure' }} />)
    expect(aria('失败')).toBeInTheDocument()
  })
})

describe('RunningIcon 旋转样式注入', () => {
  it('多次渲染仅注入一次 @keyframes 旋转样式（模块级幂等单例）', () => {
    // 本文件前序用例已渲染过 RunningIcon，样式已注入；再渲染验证不重复注入
    render(<RunningIcon />)
    render(<RunningIcon />)
    const styles = document.querySelectorAll('style')
    const spinStyles = Array.from(styles).filter((s) =>
      s.textContent?.includes('wf-icon-spin'),
    )
    expect(spinStyles.length).toBe(1)
  })
})

describe('TriggerBadge / JobTypeBadge', () => {
  it('三种触发方式徽标文案', () => {
    const { unmount } = render(<TriggerBadge trigger="submission" />)
    expect(screen.getByText('方案提交')).toBeInTheDocument()
    unmount()
    render(<TriggerBadge trigger="manual" />)
    expect(screen.getByText('手动发起')).toBeInTheDocument()
    unmount()
    render(<TriggerBadge trigger="rerun" />)
    expect(screen.getByText('重新运行')).toBeInTheDocument()
  })

  it('作业类型徽标：rules/check 与 simulation/run', () => {
    const { unmount } = render(<JobTypeBadge jobType="rules" />)
    expect(screen.getByText('rules/check')).toBeInTheDocument()
    unmount()
    render(<JobTypeBadge jobType="simulation" />)
    expect(screen.getByText('simulation/run')).toBeInTheDocument()
  })
})
