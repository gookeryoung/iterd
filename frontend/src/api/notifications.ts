/** 站内信通知相关 API：列表 / 未读计数 / 已读标记。 */

import { api } from './client';
import type { NotificationItem } from '../types';

/** 当前用户通知列表（倒序，可只看未读）。 */
export async function fetchNotifications(unreadOnly = false, limit = 50): Promise<NotificationItem[]> {
  const resp = await api.get<NotificationItem[]>('/notifications', {
    params: { unread_only: unreadOnly, limit },
  });
  return resp.data;
}

/** 当前用户未读通知数。 */
export async function fetchUnreadCount(): Promise<number> {
  const resp = await api.get<{ count: number }>('/notifications/unread-count');
  return resp.data.count;
}

/** 标记单条通知已读。 */
export async function markNotificationRead(id: number): Promise<NotificationItem> {
  const resp = await api.post<NotificationItem>(`/notifications/${id}/read`);
  return resp.data;
}

/** 全部未读标记已读，返回受影响条数。 */
export async function markAllNotificationsRead(): Promise<number> {
  const resp = await api.post<{ marked: number }>('/notifications/read-all');
  return resp.data.marked;
}
