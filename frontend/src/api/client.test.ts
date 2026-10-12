/** api/client 单元测试 —— token 存取、拦截器注入、错误归一化、401 跳转。 */

import { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { afterEach, describe, expect, it } from 'vitest'
import {
  api,
  TOKEN_KEY,
  clearCredentials,
  extractErrorMessage,
  getToken,
  isForbidden,
  setToken,
} from './client'

// ── token 存取 ──────────────────────────────────────────

describe('getToken / setToken / clearCredentials', () => {
  it('setToken 后 getToken 返回同值，clearCredentials 后为 null', () => {
    setToken('abc123')
    expect(getToken()).toBe('abc123')
    expect(localStorage.getItem(TOKEN_KEY)).toBe('abc123')
    clearCredentials()
    expect(getToken()).toBeNull()
  })
})

// ── 请求拦截器 ──────────────────────────────────────────

/** 安装自定义 adapter 捕获最终发出的请求配置 */
function installCaptureAdapter() {
  const captured: InternalAxiosRequestConfig[] = []
  api.defaults.adapter = async (config) => {
    captured.push(config)
    return {
      data: {},
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    } as never
  }
  return captured
}

/** 大小写不敏感地读取捕获到的请求头（axios AxiosHeaders 内部键名大小写不确定） */
function headerAt(headers: unknown, name: string): unknown {
  const record = headers as Record<string, unknown> | undefined
  const entries = Object.entries(record ?? {})
  const hit = entries.find(([k]) => k.toLowerCase() === name.toLowerCase())
  return hit?.[1]
}

describe('请求拦截器', () => {
  afterEach(() => {
    // 还原默认 adapter，避免影响其它用例
    delete api.defaults.adapter
  })

  it('有 token 时注入 Authorization: Bearer <token>', async () => {
    setToken('tok-1')
    const captured = installCaptureAdapter()
    await api.get('/ping')
    expect(captured).toHaveLength(1)
    expect(headerAt(captured[0]!.headers, 'Authorization')).toBe('Bearer tok-1')
  })

  it('无 token 时不注入 Authorization', async () => {
    clearCredentials()
    const captured = installCaptureAdapter()
    await api.get('/ping')
    expect(headerAt(captured[0]!.headers, 'Authorization')).toBeUndefined()
  })
})

// ── 响应拦截器：401 清除凭证并跳转 ──────────────────────

/** 安装返回指定错误响应的 adapter.
 *
 * axios 不为自定义 adapter 执行 settle：非 2xx 必须显式 reject（构造 AxiosError），
 * 与内置 adapter 的 settle 行为一致。
 */
function installErrorAdapter(status: number, data: unknown) {
  api.defaults.adapter = async (config) => {
    const response = {
      data,
      status,
      statusText: 'Error',
      headers: {},
      config,
    }
    if (status >= 200 && status < 300) return response as never
    throw new AxiosError(
      `Request failed with status code ${status}`,
      AxiosError.ERR_BAD_REQUEST,
      config,
      {},
      response as never,
    )
  }
}

describe('响应拦截器 401 处理', () => {
  afterEach(() => {
    delete api.defaults.adapter
    localStorage.removeItem(TOKEN_KEY)
  })

  it('非登录页收到 401：清除 token 并跳转 /login', async () => {
    setToken('tok-401')
    // jsdom 的 location.pathname 为不可配置 accessor，用 pushState 控制当前路径
    window.history.pushState({}, '', '/projects')
    installErrorAdapter(401, { detail: '未认证' })
    // jsdom 对 location.href 赋值仅记录不真实跳转；断言以副作用为准
    await expect(api.get('/projects')).rejects.toThrow()
    expect(getToken()).toBeNull()
  })

  it('登录页收到 401：保留现场不清除凭证（交由表单展示错误）', async () => {
    setToken('tok-login-page')
    // 拦截器读取 window.location.pathname 判断豁免，pushState 置为 /login 验证该分支
    window.history.pushState({}, '', '/login')
    installErrorAdapter(401, { detail: '用户名或密码错误' })
    await expect(api.get('/auth/me')).rejects.toThrow()
    expect(getToken()).toBe('tok-login-page')
  })
})

// ── extractErrorMessage / isForbidden ───────────────────

describe('extractErrorMessage', () => {
  it('axios 错误优先取后端 detail 字符串', () => {
    const error = new AxiosError('boom', 'ERR_BAD_REQUEST', undefined, undefined, {
      data: { detail: '后端业务错误' },
      status: 400,
      statusText: 'Bad Request',
      headers: {},
      config: {} as InternalAxiosRequestConfig,
    } as never)
    expect(extractErrorMessage(error)).toBe('后端业务错误')
  })

  it('空 detail 回退到 error.message', () => {
    const error = new AxiosError('Request failed', 'ERR_BAD_REQUEST', undefined, undefined, {
      data: { detail: '' },
      status: 400,
      statusText: 'Bad Request',
      headers: {},
      config: {} as InternalAxiosRequestConfig,
    } as never)
    expect(extractErrorMessage(error)).toBe('Request failed')
  })

  it('网络错误（ERR_NETWORK）归一化为中文提示', () => {
    const error = new AxiosError('Network Error', 'ERR_NETWORK')
    expect(extractErrorMessage(error)).toBe('网络错误：无法连接服务器')
  })

  it('普通 Error 取 message', () => {
    expect(extractErrorMessage(new Error('普通错误'))).toBe('普通错误')
  })

  it('非 Error 对象返回兜底文案', () => {
    expect(extractErrorMessage('str')).toBe('未知错误')
    expect(extractErrorMessage(undefined)).toBe('未知错误')
  })
})

describe('isForbidden', () => {
  it('403 返回 true，其余返回 false', () => {
    const forbidden = new AxiosError('forbidden', 'ERR_BAD_REQUEST', undefined, undefined, {
      data: {},
      status: 403,
      statusText: 'Forbidden',
      headers: {},
      config: {} as InternalAxiosRequestConfig,
    } as never)
    expect(isForbidden(forbidden)).toBe(true)

    const other = new AxiosError('bad', 'ERR_BAD_REQUEST', undefined, undefined, {
      data: {},
      status: 400,
      statusText: 'Bad Request',
      headers: {},
      config: {} as InternalAxiosRequestConfig,
    } as never)
    expect(isForbidden(other)).toBe(false)
    expect(isForbidden(new Error('plain'))).toBe(false)
  })
})
