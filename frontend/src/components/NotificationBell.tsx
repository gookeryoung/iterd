/** 顶栏通知中心：铃铛未读角标 + 通知列表弹层 + WebSocket 实时推送. */

import { useEffect, useState } from 'react';
import { Badge, Button, Empty, List, Popover, Typography, theme } from 'antd';
import { BellOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchNotifications,
  fetchUnreadCount,
  markAllNotificationsRead,
  markNotificationRead,
} from '../api/notifications';
import { getToken } from '../api/client';
import type { NotificationItem } from '../types';
import { formatDateTime } from '../utils/format';

/** 订阅通知推送：服务端推未读计数帧即写入缓存（断线 5 秒重连）. */
function useNotificationPush(): void {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (typeof WebSocket === 'undefined' || getToken() === null) {
      return undefined;
    }
    let socket: WebSocket | null = null;
    let disposed = false;
    let retryTimer: number | undefined;
    const connect = () => {
      if (disposed) {
        return;
      }
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
      socket = new WebSocket(`${protocol}://${window.location.host}/api/v1/ws/notifications`);
      socket.onopen = () => {
        socket?.send(JSON.stringify({ token: getToken() }));
      };
      socket.onmessage = (event) => {
        try {
          const frame = JSON.parse(String(event.data)) as { unread_count?: number };
          if (typeof frame.unread_count === 'number') {
            queryClient.setQueryData(['notifications', 'unread-count'], frame.unread_count);
          }
        } catch {
          // 非法帧忽略
        }
      };
      socket.onclose = () => {
        if (!disposed) {
          retryTimer = window.setTimeout(connect, 5000);
        }
      };
    };
    connect();
    return () => {
      disposed = true;
      if (retryTimer !== undefined) {
        window.clearTimeout(retryTimer);
      }
      socket?.close();
    };
  }, [queryClient]);
}

/** 单条通知列表项：未读高亮，点击标记已读并跳转链接. */
function NotificationRow({
  item,
  onClick,
}: {
  item: NotificationItem;
  onClick: (item: NotificationItem) => void;
}) {
  const { token } = theme.useToken();
  const unread = item.read_at === null;
  return (
    <List.Item
      onClick={() => onClick(item)}
      style={{
        cursor: 'pointer',
        padding: '10px 16px',
        background: unread ? token.colorPrimaryBg : undefined,
      }}
    >
      <div style={{ width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {unread && <Badge status="processing" />}
          <Typography.Text strong={unread} style={{ flex: 1, fontSize: 13 }}>
            {item.title}
          </Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {formatDateTime(item.created_at)}
          </Typography.Text>
        </div>
        {item.body && (
          <Typography.Paragraph type="secondary" style={{ margin: '4px 0 0', fontSize: 12.5 }}>
            {item.body}
          </Typography.Paragraph>
        )}
      </div>
    </List.Item>
  );
}

/** 通知中心铃铛（置于顶栏）。 */
export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { token } = theme.useToken();

  useNotificationPush();

  // 未读计数轮询兜底（WebSocket 推送是主通道，轮询防止漏帧）
  const unreadQuery = useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: fetchUnreadCount,
    refetchInterval: 10000,
  });
  // 打开弹层才拉列表
  const listQuery = useQuery({
    queryKey: ['notifications', 'list'],
    queryFn: () => fetchNotifications(),
    enabled: open,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['notifications'] });
  };
  const markRead = useMutation({ mutationFn: markNotificationRead, onSuccess: invalidate });
  const markAll = useMutation({ mutationFn: markAllNotificationsRead, onSuccess: invalidate });

  const items = listQuery.data ?? [];
  const unread = unreadQuery.data ?? 0;

  const handleClick = (item: NotificationItem) => {
    if (item.read_at === null) {
      markRead.mutate(item.id);
    }
    setOpen(false);
    if (item.link) {
      navigate(item.link);
    }
  };

  const content = (
    <div style={{ width: 380 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 16px',
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
        }}
      >
        <Typography.Text strong>通知中心</Typography.Text>
        <Button
          type="link"
          size="small"
          disabled={unread === 0}
          loading={markAll.isPending}
          onClick={() => markAll.mutate()}
        >
          全部已读
        </Button>
      </div>
      {listQuery.isPending ? (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <Typography.Text type="secondary">加载中…</Typography.Text>
        </div>
      ) : items.length === 0 ? (
        <Empty description="暂无通知" style={{ padding: 24 }} />
      ) : (
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => <NotificationRow item={item} onClick={handleClick} />}
          split
        />
      )}
    </div>
  );

  return (
    <Popover
      content={content}
      trigger="click"
      placement="bottomRight"
      arrow={false}
      open={open}
      onOpenChange={setOpen}
      styles={{ body: { padding: 0 } }}
    >
      <Badge count={unread} size="small" offset={[-2, 2]}>
        <Button type="text" icon={<BellOutlined style={{ fontSize: 18 }} />} aria-label="通知中心" />
      </Badge>
    </Popover>
  );
}
