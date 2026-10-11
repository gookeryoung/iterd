/** 任务进度 WebSocket 订阅：连接后发送 JWT 首帧鉴权，接收进度/日志直至终态。 */

import { useEffect, useRef, useState } from 'react';
import { getToken } from '../api/client';

/** 任务推送状态（与后端 /ws/tasks/{id} 结构一致）。 */
export interface TaskStreamState {
  id: number;
  status: string;
  progress: { stage: string; percent: number } | null;
  logs: { level: string; message: string }[] | null;
  error: string | null;
}

/** 订阅任务进度；taskId 为空时不建立连接。 */
export function useTaskStream(taskId: number | null): {
  state: TaskStreamState | null;
  connected: boolean;
} {
  const [state, setState] = useState<TaskStreamState | null>(null);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (taskId === null) {
      setState(null);
      setConnected(false);
      return;
    }
    const token = getToken();
    if (!token) {
      return;
    }
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const socket = new WebSocket(`${scheme}://${window.location.host}/api/v1/ws/tasks/${taskId}`);
    socketRef.current = socket;

    socket.onopen = () => {
      setConnected(true);
      // 令牌不进 URL：连接建立后以首帧文本发送
      socket.send(JSON.stringify({ token }));
    };
    socket.onmessage = (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as TaskStreamState;
        setState(payload);
      } catch {
        // 忽略非 JSON 帧
      }
    };
    socket.onclose = () => {
      setConnected(false);
    };

    return () => {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onclose = null;
      if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
        socket.close();
      }
      socketRef.current = null;
    };
  }, [taskId]);

  return { state, connected };
}
