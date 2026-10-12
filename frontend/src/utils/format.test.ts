/** 展示格式化工具单元测试。 */

import { describe, expect, it } from 'vitest'
import { formatDate, formatDateTime, formatSize, shortSha } from './format'

describe('formatDateTime', () => {
  it('空值返回占位符 -', () => {
    expect(formatDateTime(null)).toBe('-')
    expect(formatDateTime(undefined)).toBe('-')
    expect(formatDateTime('')).toBe('-')
  })

  it('ISO 字符串格式化为 YYYY-MM-DD HH:mm', () => {
    expect(formatDateTime('2026-10-12T08:30:00Z')).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
  })
})

describe('formatDate', () => {
  it('空值返回占位符 -', () => {
    expect(formatDate(null)).toBe('-')
    expect(formatDate(undefined)).toBe('-')
  })

  it('ISO 字符串格式化为 YYYY-MM-DD', () => {
    expect(formatDate('2026-10-12T08:30:00Z')).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})

describe('formatSize', () => {
  it('小于 1KB 直接展示字节数', () => {
    expect(formatSize(0)).toBe('0 B')
    expect(formatSize(512)).toBe('512 B')
    expect(formatSize(1023)).toBe('1023 B')
  })

  it('KB / MB / GB 进位', () => {
    expect(formatSize(1024)).toBe('1.0 KB')
    expect(formatSize(1536)).toBe('1.5 KB')
    expect(formatSize(1024 * 1024)).toBe('1.0 MB')
    expect(formatSize(3 * 1024 * 1024 * 1024)).toBe('3.0 GB')
  })

  it('超过 GB 后不再进位（TB 等按 GB 展示）', () => {
    expect(formatSize(2048 * 1024 * 1024 * 1024)).toBe('2048.0 GB')
  })
})

describe('shortSha', () => {
  it('取前 8 位', () => {
    expect(shortSha('0123456789abcdef')).toBe('01234567')
  })
})
