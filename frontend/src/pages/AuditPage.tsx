/** 审计日志页：只读 Table（时间 / 动作 / 资源类型 / 资源 ID / 操作人）。 */

import { Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useQuery } from '@tanstack/react-query';
import { fetchAuditLogs } from '../api/audit';
import type { AuditLog } from '../types';
import { formatDateTime } from '../utils/format';

export default function AuditPage() {
  const auditQuery = useQuery({
    queryKey: ['audit-logs'],
    queryFn: () => fetchAuditLogs({ limit: 200 }),
  });

  const columns: ColumnsType<AuditLog> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    { title: '操作人', dataIndex: 'actor_name', key: 'actor_name', width: 140 },
    { title: '动作', dataIndex: 'action', key: 'action', width: 180 },
    { title: '资源类型', dataIndex: 'resource_type', key: 'resource_type', width: 160 },
    { title: '资源 ID', dataIndex: 'resource_id', key: 'resource_id', width: 160 },
    { title: 'IP', dataIndex: 'ip', key: 'ip', width: 140 },
  ];

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        审计日志
      </Typography.Title>
      <Table<AuditLog>
        rowKey="id"
        columns={columns}
        dataSource={auditQuery.data ?? []}
        loading={auditQuery.isPending}
        pagination={{ pageSize: 50, hideOnSinglePage: true }}
        size="small"
        locale={{ emptyText: '暂无审计日志' }}
      />
    </div>
  );
}
