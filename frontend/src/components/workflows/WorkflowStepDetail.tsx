/** 步骤详情面板：步骤头 / 相对时间戳日志列（error 红底、仅看错误过滤）（GitHub Actions step 视觉）。 */

import { useMemo, useState } from 'react';
import { Checkbox, Typography } from 'antd';
import type { WorkflowJobStep } from '../../types';
import { formatDateTime } from '../../utils/format';
import { PRIMER_COLORS, StepStatusIcon } from './RunStatusIcon';

/** 步骤耗时文本（started_at → finished_at）。 */
function stepDuration(step: WorkflowJobStep): string {
  if (!step.started_at) {
    return '';
  }
  const end = step.finished_at ? new Date(step.finished_at).getTime() : Date.now();
  const ms = Math.max(end - new Date(step.started_at).getTime(), 0);
  if (ms < 1000) {
    return `${ms} ms`;
  }
  if (ms < 60000) {
    return `${(ms / 1000).toFixed(1)} s`;
  }
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

/** 相对时间戳格式化（秒，GitHub Actions 风格 <n>s）。 */
function tsText(ts: number | undefined): string {
  if (ts === undefined) {
    return '';
  }
  return ts < 10 ? `${ts.toFixed(1)}s` : `${Math.round(ts)}s`;
}

/** 步骤详情属性。 */
interface WorkflowStepDetailProps {
  step: WorkflowJobStep;
}

export default function WorkflowStepDetail({ step }: WorkflowStepDetailProps) {
  const [errorOnly, setErrorOnly] = useState(false);

  const logs = useMemo(() => {
    const all = step.logs ?? [];
    return errorOnly ? all.filter((entry) => entry.level === 'error') : all;
  }, [step.logs, errorOnly]);

  const hasErrorLogs = (step.logs ?? []).some((entry) => entry.level === 'error');

  return (
    <div>
      {/* 步骤头 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
        <StepStatusIcon status={step.status} conclusion={step.conclusion} />
        <Typography.Text strong style={{ fontSize: 14 }}>
          {step.name}
        </Typography.Text>
        <Typography.Text code style={{ fontSize: 12 }}>
          {step.step_key}
        </Typography.Text>
      </div>
      <div style={{ color: PRIMER_COLORS.neutral, fontSize: 12, marginBottom: 12 }}>
        {stepDuration(step) && `耗时 ${stepDuration(step)}`}
        {step.started_at && ` · 开始 ${formatDateTime(step.started_at)}`}
      </div>

      {/* 日志面板：相对时间戳列 + error 红底 + 仅看错误过滤 */}
      <div
        style={{
          border: `1px solid ${PRIMER_COLORS.border}`,
          borderRadius: 6,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            background: PRIMER_COLORS.canvas,
            borderBottom: `1px solid ${PRIMER_COLORS.border}`,
            padding: '6px 12px',
            fontSize: 12,
            fontWeight: 600,
            color: PRIMER_COLORS.text,
          }}
        >
          <span>日志</span>
          {hasErrorLogs && (
            <Checkbox
              checked={errorOnly}
              onChange={(e) => setErrorOnly(e.target.checked)}
              style={{ marginLeft: 'auto', fontWeight: 400, fontSize: 12 }}
            >
              仅看错误
            </Checkbox>
          )}
        </div>
        <div
          style={{
            background: '#fff',
            padding: '8px 0',
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
            fontSize: 12,
            lineHeight: '19px',
            maxHeight: 320,
            overflow: 'auto',
          }}
        >
          {logs.length === 0 ? (
            <div style={{ padding: '0 12px', color: PRIMER_COLORS.muted }}>
              {errorOnly && (step.logs ?? []).length > 0 ? '无错误日志' : '暂无日志'}
            </div>
          ) : (
            logs.map((entry, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
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
                <span style={{ color: PRIMER_COLORS.neutral, width: 44, flexShrink: 0, textAlign: 'right', marginRight: 10 }}>
                  {tsText(entry.ts)}
                </span>
                <span style={{ flex: 1, minWidth: 0 }}>{entry.message}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
