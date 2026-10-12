/**
 * PreviewDrawer 组件测试 —— 文本/Markdown 预览、加载失败提示与关闭态。
 */

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import PreviewDrawer from './PreviewDrawer'
import { renderProviders } from '../test/render'
import { server } from '../test/msw'
import { http, HttpResponse } from 'msw'

describe('版本预览抽屉', () => {
  it('文本文件按纯文本展示', async () => {
    server.use(
      http.get('/api/v1/versions/:id/preview', () =>
        HttpResponse.text('强度校核：满足要求', { headers: { 'content-type': 'text/plain' } }),
      ),
    )

    renderProviders(<PreviewDrawer versionId={7} filename="CAL-101_revA.txt" size={1024} onClose={() => {}} />)

    expect(await screen.findByText('预览 - CAL-101_revA.txt')).toBeInTheDocument()
    expect(await screen.findByText('强度校核：满足要求')).toBeInTheDocument()
    expect(screen.getByText((_, el) => el?.textContent === 'CAL-101_revA.txt（1.0 KB）')).toBeInTheDocument()
  })

  it('Markdown 文件按渲染后的 HTML 展示', async () => {
    server.use(
      http.get('/api/v1/versions/:id/preview', () =>
        HttpResponse.text('# 校核说明\n\n正文内容', { headers: { 'content-type': 'text/markdown' } }),
      ),
    )

    renderProviders(<PreviewDrawer versionId={8} filename="SPC-101_revA.md" size={64} onClose={() => {}} />)

    const heading = await screen.findByText('校核说明')
    expect(heading.tagName).toBe('H1')
    expect(screen.getByText('正文内容')).toBeInTheDocument()
  })

  it('预览接口失败时展示错误提示', async () => {
    server.use(
      http.get('/api/v1/versions/:id/preview', () => HttpResponse.json({}, { status: 500 })),
    )

    renderProviders(<PreviewDrawer versionId={9} filename="MOD-101_revA.step" size={2048} onClose={() => {}} />)

    expect(await screen.findByText('预览失败')).toBeInTheDocument()
  })

  it('versionId 为 null 时抽屉不打开', async () => {
    const { rerender } = renderProviders(
      <PreviewDrawer versionId={null} filename="DRW-101_revA.dxf" size={10} onClose={() => {}} />,
    )

    expect(screen.queryByText('预览 - DRW-101_revA.dxf')).not.toBeInTheDocument()

    rerender(<PreviewDrawer versionId={5} filename="DRW-101_revA.dxf" size={10} onClose={() => {}} />)
    expect(await screen.findByText('预览 - DRW-101_revA.dxf')).toBeInTheDocument()
  })
})
