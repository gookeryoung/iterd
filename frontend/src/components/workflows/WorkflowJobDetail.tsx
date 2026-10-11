/** 作业详情面板：作业头 / 日志面板 / annotations / 绑定的结构化结果表（GitHub Actions 视觉）。 */

import { Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useQuery } from '@tanstack/react-query';
import { fetchFindings } from '../../api/rules';
import { fetchSimResult } from '../../api/simulation';
import {
  SEVERITY_LABELS,
  type Finding,
  type SimResultDetail,
  type Severity,
  type WorkflowJob,
} from '../../types';
import { formatDateTime } from '../../utils/format';
import { FailureIcon, JobTypeBadge, JobStatusIcon, PRIMER_COLORS, StepStatusIcon } from './RunStatusIcon';

/** 耗时计算（started_at → finished_at）。 */
function durationText(job: WorkflowJob): string {
  if (!job.started_at) {
    return '';
  }
  const end = job.finished_at ? new Date(job.finished_at).getTime() : Date.now();
  const ms = Math.max(end - new Date(job.started_at).getTime(), 0);
  if (ms < 1000) {
    return `${ms} ms`;
  }
  if (ms < 60000) {
    return `${(ms / 1000).toFixed(1)} s`;
  }
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

/** 步骤耗时文本。 */
function stepDurationText(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) {
    return '';
  }
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const ms = Math.max(end - new Date(startedAt).getTime(), 0);
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

/** annotation 卡（GitHub 标注样式：黄/红底色条）。 */
function Annotation({ level, message, location }: { level: 'error' | 'warning'; message: string; location: string }) {
  const isError = level === 'error';
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 8,
        padding: '8px 12px',
        marginBottom: 8,
        borderRadius: 6,
        background: isError ? PRIMER_COLORS.dangerBg : PRIMER_COLORS.warnBg,
        border: `1px solid ${isError ? 'rgba(207, 34, 46, 0.4)' : PRIMER_COLORS.warnBorder}`,
      }}
    >
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ marginTop: 3, flexShrink: 0 }}>
        <path
          d="M8 1.5 15 14H1L8 1.5Z"
          stroke={isError ? PRIMER_COLORS.danger : '#9a6700'}
          strokeWidth="1.4"
          fill="none"
          strokeLinejoin="round"
        />
        <path d="M8 6v4" stroke={isError ? PRIMER_COLORS.danger : '#9a6700'} strokeWidth="1.4" strokeLinecap="round" />
        <circle cx="8" cy="12" r="0.8" fill={isError ? PRIMER_COLORS.danger : '#9a6700'} />
      </svg>
      <div>
        <div style={{ fontSize: 13, color: PRIMER_COLORS.text }}>{message}</div>
        {location && (
          <div style={{ fontSize: 12, color: PRIMER_COLORS.neutral, fontFamily: 'ui-monospace, Menlo, monospace' }}>
            {location}
          </div>
        )}
      </div>
    </div>
  );
}

/** finding 表列定义（GitHub Actions 发现项表风格）。 */
const findingColumns: ColumnsType<Finding> = [
  {
    title: '级别',
    dataIndex: 'severity',
    key: 'severity',
    width: 80,
    render: (severity: Severity) => (
      <span
        style={{
          color:
            severity === 'error' ? PRIMER_COLORS.danger : severity === 'warning' ? '#9a6700' : PRIMER_COLORS.neutral,
          fontWeight: 600,
        }}
      >
        {SEVERITY_LABELS[severity]}
      </span>
    ),
  },
  { title: '规则', key: 'rule', width: 160, render: (_: unknown, r: Finding) => `${r.rule_code} ${r.rule_name}` },
  {
    title: '产物',
    key: 'artifact',
    width: 170,
    render: (_: unknown, r: Finding) => `${r.artifact_code}（v${r.version_no}）`,
  },
  { title: '位置', dataIndex: 'location', key: 'location', width: 120 },
  { title: '消息', dataIndex: 'message', key: 'message' },
];

/** 仿真指标判定表列定义。 */
const metricColumns: ColumnsType<SimResultDetail> = [
  { title: '指标', key: 'label', render: (_: unknown, r: SimResultDetail) => `${r.label}（${r.key}）` },
  {
    title: '值',
    key: 'value',
    width: 130,
    render: (_: unknown, r: SimResultDetail) => `${r.value}${r.unit ? ` ${r.unit}` : ''}`,
  },
  { title: '下限', dataIndex: 'min', key: 'min', width: 80, render: (v: number | null) => (v === null ? '-' : v) },
  { title: '上限', dataIndex: 'max', key: 'max', width: 80, render: (v: number | null) => (v === null ? '-' : v) },
  {
    title: '判定',
    dataIndex: 'passed',
    key: 'passed',
    width: 90,
    render: (passed: boolean) => (
      <span style={{ color: passed ? PRIMER_COLORS.success : PRIMER_COLORS.danger, fontWeight: 600 }}>
        {passed ? '通过' : '超阈'}
      </span>
    ),
  },
];

/** 作业详情属性。 */
interface WorkflowJobDetailProps {
  job: WorkflowJob;
  /** 步骤点击回调（父组件切换到步骤详情）。 */
  onSelectStep?: (stepId: number) => void;
}

export default function WorkflowJobDetail({ job, onSelectStep }: WorkflowJobDetailProps) {
  // 规则作业：拉取发现项（annotations + 结构化表）
  const findingsQuery = useQuery({
    queryKey: ['workflow-job-findings', job.check_run_id],
    queryFn: () => fetchFindings(job.check_run_id as number, { severity: 'error' }),
    enabled: job.job_type === 'rules' && job.check_run_id !== null,
  });
  const findingsAllQuery = useQuery({
    queryKey: ['workflow-job-findings-all', job.check_run_id],
    queryFn: () => fetchFindings(job.check_run_id as number),
    enabled: job.job_type === 'rules' && job.check_run_id !== null,
  });
  // 仿真作业：拉取结果指标表
  const simResultQuery = useQuery({
    queryKey: ['workflow-job-sim-result', job.sim_job_id],
    queryFn: () => fetchSimResult(job.sim_job_id as number),
    enabled: job.job_type === 'simulation' && job.sim_job_id !== null && job.status === 'succeeded',
  });

  const duration = durationText(job);
  const logs = job.logs ?? [];
  const errorFindings = findingsQuery.data ?? [];

  return (
    <div>
      {/* 作业头 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
        <JobStatusIcon status={job.status} conclusion={job.conclusion} />
        <Typography.Text strong style={{ fontSize: 15 }}>
          {job.name}
        </Typography.Text>
        <JobTypeBadge jobType={job.job_type} />
      </div>
      <div style={{ color: PRIMER_COLORS.neutral, fontSize: 12, marginBottom: 12 }}>
        {job.job_key}
        {duration && ` · 耗时 ${duration}`}
        {job.started_at && ` · 开始 ${formatDateTime(job.started_at)}`}
      </div>

      {/* 绑定信息 */}
      <div
        style={{
          background: PRIMER_COLORS.canvas,
          border: `1px solid ${PRIMER_COLORS.border}`,
          borderRadius: 6,
          padding: '8px 12px',
          marginBottom: 12,
          fontSize: 12.5,
          color: PRIMER_COLORS.text,
        }}
      >
        {job.job_type === 'rules' ? (
          <span>
            规则集：<strong>{job.rule_set_name || '-'}</strong>
            {job.check_run_id !== null && (
              <>
                {' '}
                · 检查运行 <Typography.Text code>#{job.check_run_id}</Typography.Text>
              </>
            )}
          </span>
        ) : (
          <span>
            仿真模板：<strong>{job.template_name || '-'}</strong>
            {job.template_code && <Typography.Text code> {job.template_code}</Typography.Text>}
            {job.solver_type && (
              <>
                {' '}
                · 求解器 <Typography.Text code>{job.solver_type}</Typography.Text>
              </>
            )}
            {job.artifact_code && ` · 被验证产物 ${job.artifact_code}（v${job.version_no ?? '-'}）`}
            {job.sim_job_id !== null && (
              <>
                {' '}
                · 仿真作业 <Typography.Text code>#{job.sim_job_id}</Typography.Text>
              </>
            )}
          </span>
        )}
      </div>

      {/* 步骤概要（平台内置执行环节，点击进入步骤日志） */}
      {job.steps.length > 0 && (
        <div
          style={{
            border: `1px solid ${PRIMER_COLORS.border}`,
            borderRadius: 6,
            overflow: 'hidden',
            marginBottom: 12,
          }}
        >
          <div
            style={{
              background: PRIMER_COLORS.canvas,
              borderBottom: `1px solid ${PRIMER_COLORS.border}`,
              padding: '6px 12px',
              fontSize: 12,
              fontWeight: 600,
              color: PRIMER_COLORS.text,
            }}
          >
            步骤
          </div>
          {job.steps.map((step) => {
            const duration = stepDurationText(step.started_at, step.finished_at);
            return (
              <div
                key={step.id}
                onClick={() => onSelectStep?.(step.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 12px',
                  cursor: onSelectStep ? 'pointer' : 'default',
                  borderBottom: `1px solid ${PRIMER_COLORS.border}`,
                }}
                onMouseEnter={(e) => {
                  if (onSelectStep) {
                    e.currentTarget.style.background = PRIMER_COLORS.canvas;
                  }
                }}
                onMouseLeave={(e) => {
                  if (onSelectStep) {
                    e.currentTarget.style.background = '';
                  }
                }}
              >
                <StepStatusIcon status={step.status} conclusion={step.conclusion} />
                <span style={{ color: PRIMER_COLORS.text, fontSize: 12.5 }}>{step.name}</span>
                <Typography.Text code style={{ fontSize: 11 }}>
                  {step.step_key}
                </Typography.Text>
                {duration && (
                  <span style={{ marginLeft: 'auto', fontSize: 11, color: PRIMER_COLORS.neutral }}>{duration}</span>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* annotations：error 级发现项 / 超阈指标（GitHub 标注卡样式） */}
      {job.job_type === 'rules' && errorFindings.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          {errorFindings.slice(0, 5).map((f) => (
            <Annotation
              key={f.id}
              level="error"
              message={`${f.rule_code} ${f.message}`}
              location={`${f.artifact_code} v${f.version_no} · ${f.location}`}
            />
          ))}
          {errorFindings.length > 5 && (
            <div style={{ fontSize: 12, color: PRIMER_COLORS.neutral, marginBottom: 8 }}>
              …共 {errorFindings.length} 条 error 级发现项，见下方明细
            </div>
          )}
        </div>
      )}
      {job.job_type === 'simulation' && simResultQuery.data && simResultQuery.data.verdict === 'fail' && (
        <div style={{ marginBottom: 12 }}>
          {(simResultQuery.data.detail ?? [])
            .filter((d) => !d.passed)
            .slice(0, 5)
            .map((d) => (
              <Annotation
                key={d.key}
                level="warning"
                message={`指标超阈：${d.label} = ${d.value}${d.unit ? ` ${d.unit}` : ''}（${
                  d.max !== null ? `上限 ${d.max}` : `下限 ${d.min}`
                }）`}
                location={`仿真作业 #${job.sim_job_id}`}
              />
            ))}
        </div>
      )}

      {/* 日志面板（等宽字体 + 相对时间戳 + error 行红色标记） */}
      <div
        style={{
          border: `1px solid ${PRIMER_COLORS.border}`,
          borderRadius: 6,
          overflow: 'hidden',
          marginBottom: 12,
        }}
      >
        <div
          style={{
            background: PRIMER_COLORS.canvas,
            borderBottom: `1px solid ${PRIMER_COLORS.border}`,
            padding: '6px 12px',
            fontSize: 12,
            fontWeight: 600,
            color: PRIMER_COLORS.text,
          }}
        >
          日志
        </div>
        <div
          style={{
            background: '#fff',
            padding: '8px 0',
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
            fontSize: 12,
            lineHeight: '19px',
            maxHeight: 260,
            overflow: 'auto',
          }}
        >
          {logs.length === 0 ? (
            <div style={{ padding: '0 12px', color: PRIMER_COLORS.muted }}>暂无日志</div>
          ) : (
            logs.map((entry, i) => (
              <div
                key={i}
                style={{
                  padding: '0 12px',
                  whiteSpace: 'pre-wrap',
                  color: entry.level === 'error' ? PRIMER_COLORS.danger : PRIMER_COLORS.text,
                  background: entry.level === 'error' ? PRIMER_COLORS.dangerBg : undefined,
                }}
                onMouseEnter={(e) => {
                  if (entry.level !== 'error') {
                    e.currentTarget.style.background = PRIMER_COLORS.canvas;
                  }
                }}
                onMouseLeave={(e) => {
                  if (entry.level !== 'error') {
                    e.currentTarget.style.background = '';
                  }
                }}
              >
                <span style={{ color: PRIMER_COLORS.neutral, marginRight: 8 }}>
                  {job.started_at ? formatDateTime(job.started_at) : ''}
                </span>
                {entry.message}
              </div>
            ))
          )}
        </div>
      </div>

      {/* 绑定的结构化结果 */}
      {job.job_type === 'rules' && job.check_run_id !== null && (
        <div>
          <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
            检查发现项
          </Typography.Text>
          <Table<Finding>
            rowKey="id"
            columns={findingColumns}
            dataSource={findingsAllQuery.data ?? []}
            loading={findingsAllQuery.isPending}
            pagination={false}
            size="small"
            locale={{ emptyText: '无发现项' }}
          />
        </div>
      )}
      {job.job_type === 'simulation' && simResultQuery.data && (
        <div>
          <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
            仿真指标判定
          </Typography.Text>
          <Table<SimResultDetail>
            rowKey="key"
            columns={metricColumns}
            dataSource={simResultQuery.data.detail ?? []}
            pagination={false}
            size="small"
            locale={{ emptyText: '无指标明细' }}
          />
        </div>
      )}
      {job.job_type === 'simulation' && job.status === 'failed' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: PRIMER_COLORS.danger }}>
          <FailureIcon size={14} />
          <span style={{ fontSize: 13 }}>仿真作业执行失败，详见日志</span>
        </div>
      )}
    </div>
  );
}
