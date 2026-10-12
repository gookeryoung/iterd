/** useTaskStream 单元测试 —— WebSocket 订阅生命周期（mock WebSocket）。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act } from '@testing-library/react'
import { useTaskStream, type TaskStreamState } from './useTaskStream'
import { renderHookProviders } from '../test/render'
import { setToken } from '../api/client'

/** WebSocket 替身：记录实例、发送帧，手动触发 onopen/onmessage/onclose。 */
class FakeWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  static instances: FakeWebSocket[] = []

  url: string
  readyState = FakeWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  sent: string[] = []
  closed = false

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.closed = true
    this.readyState = FakeWebSocket.CLOSED
  }

  // 测试辅助：模拟连接建立
  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  // 测试辅助：模拟服务端推送
  message(payload: unknown) {
    this.onmessage?.({ data: typeof payload === 'string' ? payload : JSON.stringify(payload) })
  }
}

describe('useTaskStream', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('taskId 为 null 时不建立连接', () => {
    const { result } = renderHookProviders(() => useTaskStream(null))
    expect(FakeWebSocket.instances).toHaveLength(0)
    expect(result.current.state).toBeNull()
    expect(result.current.connected).toBe(false)
  })

  it('无 token 时不建立连接', () => {
    const { result } = renderHookProviders(() => useTaskStream(42))
    expect(FakeWebSocket.instances).toHaveLength(0)
    expect(result.current.connected).toBe(false)
  })

  it('连接地址为 ws 协议 + 任务 id；建立后发送 token 首帧', () => {
    setToken('tok-ws')
    const { result } = renderHookProviders(() => useTaskStream(42))

    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(FakeWebSocket.instances[0]!.url).toBe('ws://localhost:3000/api/v1/ws/tasks/42')
    expect(result.current.connected).toBe(false)

    act(() => {
      FakeWebSocket.instances[0]!.open()
    })
    expect(result.current.connected).toBe(true)
    // 令牌不进 URL：连接建立后以首帧 JSON 发送
    expect(FakeWebSocket.instances[0]!.sent).toEqual([JSON.stringify({ token: 'tok-ws' })])
  })

  it('收到 JSON 帧后更新 state，非 JSON 帧被忽略', () => {
    setToken('tok-ws')
    const { result } = renderHookProviders(() => useTaskStream(7))
    const socket = FakeWebSocket.instances[0]!
    act(() => socket.open())

    const payload: TaskStreamState = {
      id: 7,
      status: 'running',
      progress: { stage: 'checking', percent: 50 },
      logs: [{ level: 'info', message: 'hello' }],
      error: null,
    }
    act(() => socket.message(payload))
    expect(result.current.state).toEqual(payload)

    act(() => socket.message('not-json{{'))
    expect(result.current.state).toEqual(payload)
  })

  it('连接关闭后 connected 复位为 false', () => {
    setToken('tok-ws')
    const { result } = renderHookProviders(() => useTaskStream(9))
    const socket = FakeWebSocket.instances[0]!
    act(() => socket.open())
    expect(result.current.connected).toBe(true)

    act(() => {
      socket.onclose?.()
    })
    expect(result.current.connected).toBe(false)
  })

  it('卸载时清理回调并关闭未完成的连接', () => {
    setToken('tok-ws')
    const { unmount } = renderHookProviders(() => useTaskStream(11))
    const socket = FakeWebSocket.instances[0]!
    expect(socket.closed).toBe(false)

    unmount()
    expect(socket.onopen).toBeNull()
    expect(socket.onmessage).toBeNull()
    expect(socket.onclose).toBeNull()
    expect(socket.closed).toBe(true)
  })

  it('卸载时连接已处于 CLOSED 状态则不再调用 close', () => {
    setToken('tok-ws')
    const { unmount } = renderHookProviders(() => useTaskStream(11))
    const socket = FakeWebSocket.instances[0]!
    // 模拟服务端已先行断开（onclose 已触发、状态 CLOSED）
    socket.readyState = FakeWebSocket.CLOSED
    act(() => {
      socket.onclose?.()
    })

    unmount()
    expect(socket.onopen).toBeNull()
    expect(socket.onmessage).toBeNull()
    expect(socket.onclose).toBeNull()
    // CLOSED 分支不进入 close()，closed 标记保持 false
    expect(socket.closed).toBe(false)
  })
})
