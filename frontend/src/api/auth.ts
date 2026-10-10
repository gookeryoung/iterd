/** 认证与用户相关 API。 */

import { api } from './client';
import type { LoginResult, User } from '../types';

/** 登录入参。 */
export interface LoginInput {
  username: string;
  password: string;
}

/** 口令登录。 */
export async function login(data: LoginInput): Promise<LoginResult> {
  const resp = await api.post<LoginResult>('/auth/login', data);
  return resp.data;
}

/** 获取当前登录用户。 */
export async function fetchMe(): Promise<User> {
  const resp = await api.get<User>('/auth/me');
  return resp.data;
}

/** 用户列表（管理员接口，非管理员 403）。 */
export async function fetchUsers(): Promise<User[]> {
  const resp = await api.get<User[]>('/users');
  return resp.data;
}
