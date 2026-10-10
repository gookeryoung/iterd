/** 审计日志 API。 */

import { api } from './client';
import type { AuditLog } from '../types';

/** 审计日志列表（登录用户可查）。 */
export async function fetchAuditLogs(params?: {
  resource_type?: string;
  limit?: number;
  offset?: number;
}): Promise<AuditLog[]> {
  const resp = await api.get<AuditLog[]>('/audit-logs', { params });
  return resp.data;
}
