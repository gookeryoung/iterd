/** 审批待办中心：跨项目汇总 waiting 态会签作业，展示会签进度并提供签署入口。 */

import { Empty, Spin, Typography } from 'antd';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { fetchPendingApprovals } from '../api/workflows';
import type { PendingApproval } from '../types';
import { formatDateTime } from '../utils/format';
import { WaitingIcon } from '../components/workflows/RunStatusIcon';
import ApprovalPanel from '../components/workflows/ApprovalPanel';

/** 单条待审批卡片。 */
function PendingApprovalCard({ item }: { item: PendingApproval }) {
  const queryClient = useQueryClient();

  return (
    <div
      data-testid="pending-approval-card"
      data-workflow={item.workflow_code}
      style={{
        border: '1px solid #d0d7de',
        borderRadius: 6,
        padding: '12px 16px',
        marginBottom: 12,
        background: '#fff',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <WaitingIcon size={18} />
        <Typography.Text strong style={{ fontSize: 14 }}>
          {item.workflow_code} · {item.job_name}
        </Typography.Text>
        <Typography.Text code style={{ fontSize: 12 }}>
          {item.job_key}
        </Typography.Text>
        <span style={{ marginLeft: 'auto', fontSize: 12, color: '#57606a' }}>
          {formatDateTime(item.created_at)}
        </span>
      </div>
      <div style={{ fontSize: 12.5, color: '#57606a', marginBottom: 10 }}>
        所属迭代：
        <Link to={`/iterations/${item.iteration_id}`}>迭代 #{item.iteration_id}</Link>
        {' · '}运行 <Typography.Text code>#{item.run_id}</Typography.Text>
      </div>
      <ApprovalPanel
        jobId={item.job_id}
        minCount={item.min_count}
        approvedCount={item.approved_count}
        approvers={item.approvers}
        approvals={item.approvals}
        canApprove={item.can_approve}
        waiting
        onSigned={() => {
          void queryClient.invalidateQueries({ queryKey: ['approvals-pending'] });
        }}
      />
    </div>
  );
}

export default function PendingApprovalsPage() {
  const pendingQuery = useQuery({
    queryKey: ['approvals-pending'],
    queryFn: () => fetchPendingApprovals(),
    refetchInterval: 5000,
  });

  const items = pendingQuery.data ?? [];

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        审批待办
      </Typography.Title>
      {pendingQuery.isPending ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin />
        </div>
      ) : items.length === 0 ? (
        <Empty description="暂无待审批会签作业" />
      ) : (
        items.map((item) => <PendingApprovalCard key={item.job_id} item={item} />)
      )}
    </div>
  );
}
