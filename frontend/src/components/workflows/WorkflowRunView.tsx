/** 审查运行视图：summary 条 + 作业树（needs 层级缩进）+ 作业详情双栏（GitHub Actions run 页复刻）。 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Progress, Space, Spin, Tooltip, Typography } from 'antd';
import { CodeOutlined, RedoOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { rerunWorkflowRun } from '../../api/workflows';
import { extractErrorMessage } from '../../api/client';
import { App as AntApp } from 'antd';
import { useTaskStream } from '../../hooks/useTaskStream';
import type { WorkflowJob, WorkflowRun } from '../../types';
import { formatDateTime } from '../../utils/format';
import { JobStatusIcon, PRIMER_COLORS, RunStatusIcon } from './RunStatusIcon';
import WorkflowJobDetail from './WorkflowJobDetail';
import YamlBlock from './YamlBlock';

/** 计算 needs 层级深度（根为 0）。 */
function jobDepth(job: WorkflowJob, byKey: Map<string, WorkflowJob>): number {
  if (!job.needs || job.needs.length === 0) {
    return 0;
  }
  const depths = job.needs
    .map((key) => byKey.get(key))
    .filter((j): j is WorkflowJob => j !== undefined)
    .map((j) => jobDepth(j, byKey));
  return depths.length === 0 ? 0 : Math.max(...depths) + 1;
}

/** 总耗时（started_at → finished_at）。 */
function totalDuration(run: WorkflowRun): string {
  if (!run.started_at) {
    return '';
  }
  const end = run.finished_at ? new Date(run.finished_at).getTime() : Date.now();
  const ms = Math.max(end - new Date(run.started_at).getTime(), 0);
  if (ms < 1000) {
    return `${ms} ms`;
  }
  if (ms < 60000) {
    return `${(ms / 1000).toFixed(1)} s`;
  }
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

/** 运行视图属性。 */
interface WorkflowRunViewProps {
  run: WorkflowRun;
  /** 发起权限（designer+），控制重新运行按钮。 */
  canRun?: boolean;
}

export default function WorkflowRunView({ run, canRun = true }: WorkflowRunViewProps) {
  const { message } = AntApp.useApp();
  const queryClient = useQueryClient();
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [showYaml, setShowYaml] = useState(false);

  const busy = run.status === 'pending' || run.status === 'running';
  const { state: streamState, connected } = useTaskStream(busy ? run.task_id : null);
  const streamLogs = streamState?.logs ?? [];
  const logBoxRef = useRef<HTMLDivElement | null>(null);

  // 实时日志流：新条目到达时滚动到底部
  useEffect(() => {
    const box = logBoxRef.current;
    if (box) {
      box.scrollTop = box.scrollHeight;
    }
  }, [streamLogs.length]);

  const byKey = useMemo(() => new Map(run.jobs.map((j) => [j.job_key, j])), [run.jobs]);
  const jobsWithDepth = useMemo(
    () => run.jobs.map((job) => ({ job, depth: jobDepth(job, byKey) })),
    [run.jobs, byKey],
  );

  // 默认选中第一个作业
  useEffect(() => {
    if (selectedJobId === null && run.jobs.length > 0) {
      setSelectedJobId(run.jobs[0].id);
    }
  }, [run.jobs, selectedJobId]);

  const selectedJob = run.jobs.find((j) => j.id === selectedJobId) ?? null;

  const handleRerun = async () => {
    try {
      const newRun = await rerunWorkflowRun(run.id);
      message.success(`已重新运行（新运行 #${newRun.id}）`);
      void queryClient.invalidateQueries({ queryKey: ['workflow-runs', run.iteration_id] });
      setSelectedJobId(null);
    } catch (error) {
      message.error(extractErrorMessage(error));
    }
  };

  const summary = run.summary;
  return (
    <div className="wf-run-view" style={{ fontSize: 13 }}>
      {/* summary 条 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '10px 16px',
          border: `1px solid ${PRIMER_COLORS.border}`,
          borderRadius: 6,
          background: '#fff',
          marginBottom: 12,
          flexWrap: 'wrap',
        }}
      >
        <RunStatusIcon status={run.status} summary={summary} />
        <Typography.Text strong style={{ fontSize: 14 }}>
          {run.workflow_code} #{run.id}
        </Typography.Text>
        {busy && (
          <Space size={4}>
            <Spin size="small" />
            <span style={{ color: PRIMER_COLORS.accent }}>执行中…</span>
          </Space>
        )}
        {summary && (
          <span style={{ color: PRIMER_COLORS.neutral }}>
            <span style={{ color: PRIMER_COLORS.success, fontWeight: 600 }}>{summary.jobs.success} successful</span>
            {' / '}
            <span style={{ color: PRIMER_COLORS.danger, fontWeight: 600 }}>{summary.jobs.failure} failed</span>
            {' / '}
            <span style={{ color: PRIMER_COLORS.neutral, fontWeight: 600 }}>{summary.jobs.skipped} skipped</span>
          </span>
        )}
        <span style={{ color: PRIMER_COLORS.neutral, fontSize: 12 }}>
          {run.started_at ? formatDateTime(run.started_at) : formatDateTime(run.created_at)}
          {totalDuration(run) && ` · 总耗时 ${totalDuration(run)}`}
        </span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <Tooltip title={showYaml ? '收起 YAML' : '查看 YAML 定义快照'}>
            <Button
              size="small"
              icon={<CodeOutlined />}
              onClick={() => setShowYaml(!showYaml)}
              style={{ color: PRIMER_COLORS.neutral }}
            >
              YAML
            </Button>
          </Tooltip>
          {canRun && (
            <Button size="small" icon={<RedoOutlined />} disabled={busy} onClick={handleRerun}>
              重新运行
            </Button>
          )}
        </span>
      </div>

      {/* 运行中：实时进度 + 日志流（WebSocket 推送，GitHub Actions live log 风格） */}
      {busy && (
        <div
          style={{
            border: `1px solid ${PRIMER_COLORS.border}`,
            borderRadius: 6,
            background: '#fff',
            padding: '10px 16px',
            marginBottom: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Spin size="small" />
            <span style={{ fontSize: 12.5, color: PRIMER_COLORS.text }}>
              {streamState?.progress?.stage || '排队等待调度'}
              {streamState?.progress?.percent !== undefined &&
                streamState?.progress?.percent !== null &&
                ` · ${streamState.progress.percent}%`}
            </span>
            <span
              style={{
                marginLeft: 'auto',
                fontSize: 12,
                color: connected ? PRIMER_COLORS.success : PRIMER_COLORS.muted,
              }}
            >
              {connected ? '实时日志已连接' : '实时日志未连接'}
            </span>
          </div>
          {streamState?.progress && (
            <Progress percent={streamState.progress.percent} size="small" status="active" showInfo={false} />
          )}
          <div
            ref={logBoxRef}
            style={{
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
              fontSize: 12,
              lineHeight: '19px',
              maxHeight: 180,
              overflow: 'auto',
              marginTop: 8,
              borderTop: streamLogs.length > 0 ? `1px solid ${PRIMER_COLORS.border}` : undefined,
              paddingTop: streamLogs.length > 0 ? 6 : 0,
            }}
          >
            {streamLogs.length === 0 ? (
              <div style={{ color: PRIMER_COLORS.muted }}>等待日志输出…</div>
            ) : (
              streamLogs.map((entry, i) => (
                <div
                  key={i}
                  style={{
                    whiteSpace: 'pre-wrap',
                    color: entry.level === 'error' ? PRIMER_COLORS.danger : PRIMER_COLORS.text,
                    background: entry.level === 'error' ? PRIMER_COLORS.dangerBg : undefined,
                  }}
                >
                  {entry.message}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* YAML 快照折叠区 */}
      {showYaml && (
        <div style={{ marginBottom: 12 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
            运行定义快照（发起时固化）
          </Typography.Text>
          <YamlBlock content={run.definition} maxHeight={280} />
        </div>
      )}

      {/* 双栏：作业树 + 作业详情 */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'stretch' }}>
        {/* 左栏：作业树 */}
        <div
          style={{
            width: 268,
            flexShrink: 0,
            border: `1px solid ${PRIMER_COLORS.border}`,
            borderRadius: 6,
            background: '#fff',
            overflow: 'auto',
            maxHeight: 560,
          }}
        >
          <div
            style={{
              padding: '8px 12px',
              fontSize: 12,
              fontWeight: 600,
              color: PRIMER_COLORS.neutral,
              borderBottom: `1px solid ${PRIMER_COLORS.border}`,
            }}
          >
            作业
          </div>
          {jobsWithDepth.map(({ job, depth }) => {
            const selected = job.id === selectedJobId;
            return (
              <div
                key={job.id}
                onClick={() => setSelectedJobId(job.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '7px 12px',
                  paddingLeft: 12 + depth * 18,
                  cursor: 'pointer',
                  borderLeft: selected ? `2px solid ${PRIMER_COLORS.accent}` : '2px solid transparent',
                  background: selected ? 'rgba(9, 105, 218, 0.08)' : undefined,
                }}
              >
                <JobStatusIcon status={job.status} conclusion={job.conclusion} />
                <span
                  style={{
                    flex: 1,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    color: PRIMER_COLORS.text,
                  }}
                >
                  {job.name}
                </span>
                {job.finished_at && job.started_at && (
                  <span style={{ fontSize: 11, color: PRIMER_COLORS.neutral }}>
                    {(() => {
                      const ms = new Date(job.finished_at).getTime() - new Date(job.started_at).getTime();
                      return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
                    })()}
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* 右栏：选中作业详情 */}
        <div
          style={{
            flex: 1,
            minWidth: 0,
            border: `1px solid ${PRIMER_COLORS.border}`,
            borderRadius: 6,
            background: '#fff',
            padding: 16,
            overflow: 'auto',
            maxHeight: 560,
          }}
        >
          {selectedJob ? (
            <WorkflowJobDetail key={selectedJob.id} job={selectedJob} />
          ) : (
            <div style={{ color: PRIMER_COLORS.neutral, textAlign: 'center', padding: 32 }}>
              选择左侧作业查看详情
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
