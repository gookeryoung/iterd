/**
 * Vitest 全局测试 setup：
 * - 注册 jest-dom 匹配器
 * - antd 5 在 jsdom 下的所需 polyfill（matchMedia / ResizeObserver / getBoundingClientRect / scrollTo）
 * - RTL 自动 cleanup（globals 模式下 @testing-library/react 依赖 afterEach）
 * - 每个用例后清空 localStorage / sessionStorage，保证用例间隔离
 */
import '@testing-library/jest-dom/vitest'
import { act, cleanup } from '@testing-library/react'
import { message } from 'antd'
import { afterAll, afterEach, beforeAll, vi } from 'vitest'
import { server } from './msw'

// ── polyfill：matchMedia（antd 响应式断点依赖）────────────────────────
if (typeof window !== 'undefined' && !window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(), // 已废弃但仍被部分 antd 代码使用
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  })
}

// ── polyfill：ResizeObserver（antd 布局测量依赖）──────────────────────
if (typeof window !== 'undefined' && !window.ResizeObserver) {
  class ResizeObserverPolyfill {
    observe = vi.fn()
    unobserve = vi.fn()
    disconnect = vi.fn()
  }
  window.ResizeObserver = ResizeObserverPolyfill as unknown as typeof ResizeObserver
}

// ── polyfill：元素尺寸与滚动（antd 弹层定位依赖）──────────────────────
if (typeof window !== 'undefined') {
  if (!window.scrollTo) {
    window.scrollTo = vi.fn()
  }
  if (!Element.prototype.scrollTo) {
    Element.prototype.scrollTo = vi.fn()
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn()
  }
  if (!Element.prototype.getBoundingClientRect) {
    Element.prototype.getBoundingClientRect = () => ({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      width: 0,
      height: 0,
      toJSON: () => ({}),
    }) as DOMRect
  }
  // jsdom 未实现 IntersectionObserver，polyfill：observe 后立即触发 isIntersecting=true
  if (!window.IntersectionObserver) {
    class IntersectionObserverPolyfill {
      root = null
      rootMargin = ''
      thresholds: number[] = []
      private callback: IntersectionObserverCallback
      constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
        this.callback = callback
        this.thresholds = options?.threshold !== undefined
          ? (Array.isArray(options.threshold) ? options.threshold : [options.threshold])
          : []
      }
      observe = (target: Element) => {
        this.callback([{ target, isIntersecting: true } as IntersectionObserverEntry], this)
      }
      unobserve = vi.fn()
      disconnect = vi.fn()
      takeRecords = () => []
    }
    window.IntersectionObserver =
      IntersectionObserverPolyfill as unknown as typeof IntersectionObserver
  }
}

// ── 抑制已知的无害 console.error 噪音（antd act 警告）──────────────────
// antd 的 AntApp 挂载 rc-notification holder 及 rc-motion，会在
// requestAnimationFrame 中更新状态，发生在 RTL act 作用域之外，产生
// "not wrapped in act(...)" 警告。该更新仅涉弹层动画时序，不影响任何断言；
// 仅过滤栈内命中 node_modules 下 antd / rc-* 的此类警告，业务组件自身
// 的 act 警告仍正常抛出。
const originalConsoleError = console.error.bind(console)
console.error = (...args: unknown[]) => {
  const text = args.map((a) => (typeof a === 'string' ? a : String(a))).join('\n')
  if (text.includes('not wrapped in act') && /node_modules[\\/].*(?:antd|rc-[a-z-]+)/.test(text)) {
    return
  }
  // 抑制 MSW onUnhandledRequest: 'error' 在 stderr 打印的"未命中 handler"错误——
  // 该配置已让请求 Promise reject（测试侧用 expect(...).rejects 断言），
  // stderr 输出纯属噪音，掩盖真正的业务报错线索。
  if (text.includes('[MSW] Error: intercepted a request without a matching request handler')) {
    return
  }
  originalConsoleError(...args)
}

// ── 修复 jsdom 伪元素 getComputedStyle 未实现警告 ──────────────────────
// antd 内部测量样式时会调 getComputedStyle(ele, '::-webkit-scrollbar')。
// jsdom 收到非空伪元素参数时经 virtualConsole 发 jsdomError——多 worker 下该
// 错误直写 worker stderr，patch console.error 拦不住。jsdom 对伪元素本来就
// 只返回元素本身的样式声明，这里直接降级为无伪元素调用，行为一致且不再告警。
if (typeof window !== 'undefined') {
  const origGetComputedStyle = window.getComputedStyle.bind(window)
  window.getComputedStyle = function (elt: Element, pseudoElt?: string | null): CSSStyleDeclaration {
    void pseudoElt
    return origGetComputedStyle(elt)
  }
}

// ── 抑制 jsdom "navigation to another Document" 未实现警告 ─────────────
// 测试中 401 拦截器（window.location.href = '/login'）等程序化跳转，jsdom 无法
// 跨文档导航，会经 virtualConsole 发 jsdomError。vitest 把 virtualConsole 转发到
// worker console 并直写 stderr（绕过 console.error patch），需在 emit 层拦截。
// 仅过滤该类已知噪音，其他 jsdomError 照常抛出。
if (typeof window !== 'undefined') {
  const vc = (window as unknown as { _settings?: { virtualConsole?: { emit?: (evt: string, e: { message?: string }) => void } } })._settings?.virtualConsole
  if (vc && typeof vc.emit === 'function') {
    const origEmit = vc.emit.bind(vc)
    vc.emit = (evt: string, e: { message?: string }) => {
      if (evt === 'jsdomError' && typeof e?.message === 'string' && e.message.includes('navigation to another Document')) {
        return
      }
      return origEmit(evt, e)
    }
  }
}

beforeAll(() => {
  // MSW 网络层拦截：漏配端点直接报错，防止测试悄悄打到真实网络
  server.listen({ onUnhandledRequest: 'error' })
})

// 每个用例后自动清理：DOM 卸载 + 本地存储清空 + MSW handlers 还原
afterEach(async () => {
  cleanup()
  // message.destroy() 先于 DOM 摘除：卸载静态 message 容器内的全部挂起通知，
  // 触发 React unmount 清理 rc-notification 的自动关闭定时器——否则定时器在
  // 测试文件结束、jsdom 环境销毁后仍会触发，回调访问 window 抛
  // "ReferenceError: window is not defined"，vitest 计为 unhandled error。
  await act(async () => {
    message.destroy()
  })
  // antd 静态 message 渲染在 React 树之外的容器，cleanup() 无法卸载；
  // jsdom 不跑动画导致 destroyAll 的离场动画永不结束，残留的提示会干扰后续用例
  document.querySelectorAll('.ant-modal-root, .ant-message, .ant-notification').forEach((n) => n.remove())
  window.localStorage.clear()
  window.sessionStorage.clear()
  server.resetHandlers()
})

afterAll(() => {
  server.close()
  server.events.removeAllListeners()
})
