/** 项目工作区 - 审查 Tab：跨迭代运行列表（GitHub Actions 风格），展开复用运行详情。 */

import { useEffect, useState } from 'react';
import { Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useQuery } from '@tanstack/react-query';
import { fetchProjectRuns, fetchWorkflowRun } from '../api/workflows';
import type { ProjectRunItem, WorkflowTrigger } from '../types';
import { RunStatusIcon } from './workflows/RunStatusIcon';
import WorkflowRunView from './workflows/WorkflowRunView';
import { formatDateTime } from '../utils/format';

/** 审查 Tab 属性。 */
interface ProjectRunsTabProps {
  projectId: number;
}

/** 触发方式中文标签。 */
const TRIGGER_LABELS: Record<WorkflowTrigger, string> = {
  submission: '方案提交',
  manual: '手动',
  rerun: '重新运行',
};

export default function ProjectRunsTab({ projectId }: ProjectRunsTabProps) {
  const [expandedRunId, setExpandedRunId] = useState<number | null>(null);

  const runsQuery = useQuery({
    queryKey: ['project-runs', projectId],
    queryFn: () => fetchProjectRuns(projectId),
    refetchInterval: (query) => {
      const runs = query.state.data ?? [];
      return runs.some((r) => r.status === 'pending' || r.status === 'running') ? 2000 : false;
    },
  });

  // 展开时拉取完整运行详情（含作业与步骤）
  const detailQuery = useQuery({
    queryKey: ['workflow-run', expandedRunId],
    queryFn: () => fetchWorkflowRun(expandedRunId as number),
    enabled: expandedRunId !== null,
  });

  const runs = runsQuery.data ?? [];

  // 默认展开最新一条
  useEffect(() => {
    if (expandedRunId === null && runs.length > 0) {
      setExpandedRunId(runs[0].id);
    }
  }, [runs, expandedRunId]);

  const columns: ColumnsType<ProjectRunItem> = [
    {
      title: '运行',
      key: 'run',
      render: (_: unknown, record: ProjectRunItem) => (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          <RunStatusIcon status={record.status} summary={record.summary} />
          <Typography.Text strong style={{ fontSize: 13 }}>
            {record.workflow_code} #{record.id}
          </Typography.Text>
        </span>
      ),
    },
    {
      title: '所属迭代',
      key: 'iteration',
      width: 240,
      render: (_: unknown, record: ProjectRunItem) =>
        `#${record.iteration_number} ${record.iteration_title}`,
    },
    {
      title: '触发方式',
      dataIndex: 'trigger',
      key: 'trigger',
      width: 110,
      render: (value: WorkflowTrigger) => <Tag>{TRIGGER_LABELS[value] ?? value}</Tag>,
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 160,
      render: (value: string | null) => (value ? formatDateTime(value) : '-'),
    },
    {
      title: '结束时间',
      dataIndex: 'finished_at',
      key: 'finished_at',
      width: 160,
      render: (value: string | null) => (value ? formatDateTime(value) : '-'),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (value: string) => formatDateTime(value),
    },
  ];

  return (
    <Table<ProjectRunItem>
      rowKey="id"
      columns={columns}
      dataSource={runs}
      loading={runsQuery.isPending}
      pagination={false}
      size="small"
      locale={{ emptyText: '暂无审查运行' }}
      expandable={{
        expandedRowKeys: expandedRunId !== null ? [expandedRunId] : [],
        onExpandedRowsChange: (keys) => setExpandedRunId(keys.length > 0 ? (keys[0] as number) : null),
        expandedRowRender: (record: ProjectRunItem) =>
          record.id === expandedRunId && detailQuery.data ? (
            <WorkflowRunView run={detailQuery.data} />
          ) : (
            <Typography.Text type="secondary">加载运行详情…</Typography.Text>
          ),
        rowExpandable: () => true,
      }}
    />
  );
}
