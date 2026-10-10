/** axios 实例：统一 baseURL、Bearer 认证头与 401 跳转。 */

import axios from 'axios';

/** localStorage 中 token 的键名。 */
export const TOKEN_KEY = 'iterd_token';

/** 读取本地 token。 */
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/** 保存 token。 */
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

/** 清除本地凭证（token 与缓存用户）。 */
export function clearCredentials(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/** 全局 axios 实例（/api/v1 前缀）。 */
export const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
});

// 请求拦截：附加 Bearer 认证头
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截：401 清除凭证并跳回登录页（登录页自身除外）
api.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      const { pathname } = window.location;
      if (!pathname.startsWith('/login')) {
        clearCredentials();
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

/** 从错误对象中提取后端 detail 消息。 */
export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as { detail?: unknown } | undefined;
    if (typeof data?.detail === 'string' && data.detail.length > 0) {
      return data.detail;
    }
    if (error.code === 'ERR_NETWORK') {
      return '网络错误：无法连接服务器';
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return '未知错误';
}

/** 判断错误是否为 403（无权限）。 */
export function isForbidden(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 403;
}
