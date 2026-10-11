/** 迭代详情 - 审查流水线 Tab：提交方案（触发事件）/ 提交分组运行列表 / GitHub 风格运行详情（主审查入口）。 */

import { useEffect, useState } from 'react';
import { Button, Empty, Form, Input, Modal, Space, Typography } from 'antd';
import { LinkOutlined, SendOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App as AntApp } from 'antd';
import { Link } from 'react-router-dom';
import { createSubmission, fetchSubmissions, fetchWorkflowRuns } from '../api/workflows';
import { extractErrorMessage } from '../api/client';
import { formatDateTime } from '../utils/format';
import type { WorkflowRun } from '../types';
import { RunStatusIcon } from './workflows/RunStatusIcon';
import WorkflowRunView from './workflows/WorkflowRunView';

/** 审查流水线 Tab 属性。 */
interface WorkflowsTabProps {
  iterationId: number;
}

/** 提交方案表单值。 */
interface SubmissionFormValues {
  title: string;
  note?: string;
}

/** 运行行（可展开详情，GitHub Actions run 列表风格）。 */
function RunRow({
  run,
  expanded,
  onToggle,
}: {
  run: WorkflowRun;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div style={{ borderBottom: '1px solid #d0d7de' }}>
      <div
        onClick={onToggle}
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
}

export default function WorkflowsTab({ iterationId }: WorkflowsTabProps) {
  const { message } = AntApp.useApp();
  const queryClient = useQueryClient();
  const [expandedRunId, setExpandedRunId] = useState<number | null>(null);
  const [submitOpen, setSubmitOpen] = useState(false);
  const [form] = Form.useForm<SubmissionFormValues>();

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['submissions', iterationId] });
    void queryClient.invalidateQueries({ queryKey: ['workflow-runs', iterationId] });
  };

  const submissionsQuery = useQuery({
    queryKey: ['submissions', iterationId],
    queryFn: () => fetchSubmissions(iterationId),
    refetchInterval: (query) => {
      const items = query.state.data ?? [];
      const busy = items.some((s) =>
        s.runs.some((r) => r.status === 'pending' || r.status === 'running'),
      );
      return busy ? 2000 : false;
    },
  });

  // 手动发起 / rerun 无提交方案的运行（submission_id 为空）
  const runsQuery = useQuery({
    queryKey: ['workflow-runs', iterationId],
    queryFn: () => fetchWorkflowRuns(iterationId),
    refetchInterval: (query) => {
      const runs = query.state.data ?? [];
      return runs.some((r) => r.status === 'pending' || r.status === 'running') ? 2000 : false;
    },
  });

  const submissions = submissionsQuery.data ?? [];
  const manualRuns = (runsQuery.data ?? []).filter((r) => r.submission_id === null);

  // 默认展开最新运行
  useEffect(() => {
    if (expandedRunId === null) {
      const allRuns = [...runsQuery.data ?? [], ...submissions.flatMap((s) => s.runs)];
      if (allRuns.length > 0) {
        setExpandedRunId(allRuns[allRuns.length - 1].id);
      }
    }
  }, [runsQuery.data, submissions, expandedRunId]);

  const submitMutation = useMutation({
    mutationFn: (values: SubmissionFormValues) =>
      createSubmission(iterationId, { title: values.title, note: values.note ?? '' }),
    onSuccess: (submission) => {
      message.success(`方案已提交，触发 ${submission.runs.length} 条审查运行`);
      setSubmitOpen(false);
      form.resetFields();
      // 展开本次提交触发的第一条运行
      if (submission.runs.length > 0) {
        setExpandedRunId(submission.runs[0].id);
      }
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const toggleRun = (runId: number) => setExpandedRunId(expandedRunId === runId ? null : runId);

  const hasRuns = submissions.some((s) => s.runs.length > 0) || manualRuns.length > 0;

  return (
    <div>
      {/* 提交方案发起条 */}
      <Space style={{ marginBottom: 16 }} wrap>
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={() => setSubmitOpen(true)}
        >
          提交审查方案
        </Button>
        <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
          提交迭代方案触发审查流水线：每个启用模板各产生一条运行（GitHub Actions push 语义）
        </Typography.Text>
        <Link to="/workflows">
          <Button icon={<LinkOutlined />}>管理审查模板</Button>
        </Link>
      </Space>

      {/* 提交分组运行列表 */}
      {!hasRuns ? (
        <Empty description="暂无审查运行：提交审查方案以触发流水线" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {submissions.map((submission) => (
            <div key={submission.id}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'baseline',
                  gap: 10,
                  marginBottom: 6,
                }}
              >
                <Typography.Text strong style={{ fontSize: 14 }}>
                  {submission.title}
                </Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {formatDateTime(submission.created_at)}
                  {submission.note ? ` · ${submission.note}` : ''}
                </Typography.Text>
              </div>
              {submission.runs.length === 0 ? (
                <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
                  本次提交未触发任何运行（无启用模板）
                </Typography.Text>
              ) : (
                <div
                  style={{
                    border: '1px solid #d0d7de',
                    borderRadius: 6,
                    background: '#fff',
                    overflow: 'hidden',
                  }}
                >
                  {submission.runs.map((run) => (
                    <RunRow
                      key={run.id}
                      run={run}
                      expanded={run.id === expandedRunId}
                      onToggle={() => toggleRun(run.id)}
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
          {manualRuns.length > 0 && (
            <div>
              <Typography.Text strong style={{ fontSize: 14, display: 'block', marginBottom: 6 }}>
                手动运行
              </Typography.Text>
              <div
                style={{
                  border: '1px solid #d0d7de',
                  borderRadius: 6,
                  background: '#fff',
                  overflow: 'hidden',
                }}
              >
                {manualRuns.map((run) => (
                  <RunRow
                    key={run.id}
                    run={run}
                    expanded={run.id === expandedRunId}
                    onToggle={() => toggleRun(run.id)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 提交方案 Modal */}
      <Modal
        title="提交审查方案"
        open={submitOpen}
        onCancel={() => setSubmitOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={submitMutation.isPending}
        destroyOnHidden
      >
        <Form<SubmissionFormValues> form={form} layout="vertical" onFinish={(values) => submitMutation.mutate(values)}>
          <Form.Item
            name="title"
            label="方案标题"
            rules={[{ required: true, message: '请输入方案标题' }]}
          >
            <Input placeholder="例如：传动方案第三版设计" maxLength={128} />
          </Form.Item>
          <Form.Item name="note" label="提交说明（可选）">
            <Input.TextArea rows={3} placeholder="本次提交的变更要点…" maxLength={1024} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
