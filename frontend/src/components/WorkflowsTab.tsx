/** 迭代详情 - 审查流水线 Tab：模板选择 / 发起运行 / 运行列表 / GitHub 风格运行详情（主审查入口）。 */

import { useEffect, useState } from 'react';
import { Button, Empty, Select, Space, Typography } from 'antd';
import { CaretRightOutlined, LinkOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App as AntApp } from 'antd';
import { Link } from 'react-router-dom';
import { createWorkflowRun, fetchWorkflowRuns, fetchWorkflows } from '../api/workflows';
import { extractErrorMessage } from '../api/client';
import { formatDateTime } from '../utils/format';
import { RunStatusIcon } from './workflows/RunStatusIcon';
import WorkflowRunView from './workflows/WorkflowRunView';

/** 审查流水线 Tab 属性。 */
interface WorkflowsTabProps {
  iterationId: number;
  projectId: number;
}

export default function WorkflowsTab({ iterationId, projectId }: WorkflowsTabProps) {
  const { message } = AntApp.useApp();
  const queryClient = useQueryClient();
  const [templateId, setTemplateId] = useState<number | undefined>(undefined);
  const [expandedRunId, setExpandedRunId] = useState<number | null>(null);

  const templatesQuery = useQuery({
    queryKey: ['workflows', projectId],
    queryFn: () => fetchWorkflows(projectId),
  });

  const runsQuery = useQuery({
    queryKey: ['workflow-runs', iterationId],
    queryFn: () => fetchWorkflowRuns(iterationId),
    refetchInterval: (query) => {
      const runs = query.state.data ?? [];
      return runs.some((r) => r.status === 'pending' || r.status === 'running') ? 2000 : false;
    },
  });

  const templates = (templatesQuery.data ?? []).filter((t) => t.enabled);
  const runs = runsQuery.data ?? [];
  // 默认展开最新运行
  useEffect(() => {
    if (expandedRunId === null && runs.length > 0) {
      setExpandedRunId(runs[runs.length - 1].id);
    }
  }, [runs, expandedRunId]);

  useEffect(() => {
    if (templateId === undefined && templates.length > 0) {
      setTemplateId(templates[0].id);
    }
  }, [templates, templateId]);

  const startMutation = useMutation({
    mutationFn: () => createWorkflowRun(iterationId, templateId as number),
    onSuccess: (run) => {
      message.success(`审查运行已发起（运行 #${run.id}）`);
      setExpandedRunId(run.id);
      void queryClient.invalidateQueries({ queryKey: ['workflow-runs', iterationId] });
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  return (
    <div>
      {/* 发起条 */}
      <Space style={{ marginBottom: 16 }} wrap>
        <Select<number>
          style={{ width: 280 }}
          placeholder="选择审查模板"
          value={templateId}
          onChange={setTemplateId}
          loading={templatesQuery.isPending}
          options={templates.map((t) => ({
            value: t.id,
            label: t.project_id === null ? `${t.name}（全局）` : `${t.code} ${t.name}`,
          }))}
        />
        <Button
          type="primary"
          icon={<CaretRightOutlined />}
          loading={startMutation.isPending}
          disabled={!templateId}
          onClick={() => startMutation.mutate()}
        >
          发起审查
        </Button>
        <Link to="/workflows">
          <Button icon={<LinkOutlined />}>管理审查模板</Button>
        </Link>
      </Space>

      {/* 运行列表（GitHub Actions run 列表风格：图标 + 标题 + 时间） */}
      {runs.length === 0 ? (
        <Empty description="暂无审查运行：选择模板并发起审查" />
      ) : (
        <div
          style={{
            border: '1px solid #d0d7de',
            borderRadius: 6,
            background: '#fff',
            marginBottom: 12,
            overflow: 'hidden',
          }}
        >
          {[...runs].reverse().map((run) => {
            const expanded = run.id === expandedRunId;
            return (
              <div key={run.id} style={{ borderBottom: '1px solid #d0d7de' }}>
                <div
                  onClick={() => setExpandedRunId(expanded ? null : run.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '10px 16px',
                    cursor: 'pointer',
                    background: expanded ? '#f6f8fa' : undefined,
                  }}
                >
                  <RunStatusIcon status={run.status} summary={run.summary} />
                  <Typography.Text strong style={{ fontSize: 13 }}>
                    {run.workflow_code} #{run.id}
                  </Typography.Text>
                  {run.summary && (
                    <span style={{ fontSize: 12, color: '#57606a' }}>
                      {run.summary.jobs.success} successful / {run.summary.jobs.failure} failed /{' '}
                      {run.summary.jobs.skipped} skipped
                    </span>
                  )}
                  <span style={{ marginLeft: 'auto', fontSize: 12, color: '#57606a' }}>
                    {formatDateTime(run.created_at)}
                  </span>
                </div>
                {expanded && (
                  <div style={{ padding: 12, background: '#f6f8fa' }}>
                    <WorkflowRunView run={run} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* 无列表展开时（空态）不渲染详情 */}
      {runs.length === 0 && !templatesQuery.isPending && templates.length === 0 && (
        <Typography.Text type="secondary">
          当前项目尚无可用审查模板，请先到「审查模板」页创建。
        </Typography.Text>
      )}
    </div>
  );
}
