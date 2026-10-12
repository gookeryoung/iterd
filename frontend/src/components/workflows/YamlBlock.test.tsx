/**
 * YamlBlock 组件测试 —— YAML 文本渲染、行号展示与多行切分。
 */

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import YamlBlock from './YamlBlock'
import { renderProviders } from '../../test/render'

const SAMPLE = `name: 传动系统审查
jobs:
  # 静态规则检查
  rules-check:
    uses: rules/check`

/** 行级文本匹配（高亮切分把文本拆进多个 span，按行容器 textContent 整体比对）。 */
function lineText(text: string): (_: string, el: Element | null) => boolean {
  return (_, el) => el?.textContent === text
}

describe('YamlBlock', () => {
  it('渲染 YAML 内容与行号', () => {
    renderProviders(<YamlBlock content={SAMPLE} />)

    expect(screen.getByText(lineText('name: 传动系统审查'))).toBeInTheDocument()
    expect(screen.getByText(lineText('jobs:'))).toBeInTheDocument()
    expect(screen.getByText(lineText('    uses: rules/check'))).toBeInTheDocument()
    expect(screen.getByText('# 静态规则检查')).toBeInTheDocument()
  })

  it('按行切分并展示递增行号', () => {
    renderProviders(<YamlBlock content={SAMPLE} />)

    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('空内容仅渲染单行行号', () => {
    renderProviders(<YamlBlock content="" />)

    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.queryByText('2')).not.toBeInTheDocument()
  })
})
