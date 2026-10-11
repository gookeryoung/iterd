/** GitHub octicon 风格状态图标（内联 SVG 自绘，不新增图标依赖）。 */

import type { WorkflowConclusion, WorkflowJobStatus, WorkflowRunStatus } from '../../types';

/** Primer 语义色。 */
export const PRIMER_COLORS = {
  success: '#1a7f37',
  successBg: '#dafbe1',
  danger: '#cf222e',
  dangerBg: '#ffebe9',
  accent: '#0969da',
  neutral: '#57606a',
  muted: '#8c959f',
  border: '#d0d7de',
  canvas: '#f6f8fa',
  text: '#1f2328',
  warnBg: '#fff8c5',
  warnBorder: 'rgba(210, 153, 34, 0.4)',
} as const;

/** 旋转动画 keyframes（模块级单例）。 */
const SPIN_KEYFRAMES = `
@keyframes wf-icon-spin { to { transform: rotate(360deg); } }
`;

let spinStyleInjected = false;

function injectSpinStyle() {
  if (spinStyleInjected || typeof document === 'undefined') {
    return;
  }
  const style = document.createElement('style');
  style.textContent = SPIN_KEYFRAMES;
  document.head.appendChild(style);
  spinStyleInjected = true;
}

/** 成功对勾（圆角方形底）。 */
export function SuccessIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-label="成功">
      <rect width="16" height="16" rx="3" fill={PRIMER_COLORS.successBg} />
      <path
        d="M4.5 8.2 7 10.7l4.5-5"
        stroke={PRIMER_COLORS.success}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}

/** 失败叉号（圆角方形底）。 */
export function FailureIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-label="失败">
      <rect width="16" height="16" rx="3" fill={PRIMER_COLORS.dangerBg} />
      <path
        d="M5 5l6 6M11 5l-6 6"
        stroke={PRIMER_COLORS.danger}
        strokeWidth="1.8"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

/** 进行中旋转环。 */
export function RunningIcon({ size = 16 }: { size?: number }) {
  injectSpinStyle();
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      aria-label="进行中"
      style={{ animation: 'wf-icon-spin 0.8s linear infinite' }}
    >
      <circle cx="8" cy="8" r="6" stroke={PRIMER_COLORS.accent} strokeWidth="2" opacity="0.25" />
      <path d="M8 2a6 6 0 0 1 6 6" stroke={PRIMER_COLORS.accent} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

/** 排队空心圆。 */
export function PendingIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-label="排队中">
      <circle cx="8" cy="8" r="5.5" stroke={PRIMER_COLORS.neutral} strokeWidth="1.6" />
    </svg>
  );
}

/** 跳过虚线圆。 */
export function SkippedIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-label="已跳过">
      <circle cx="8" cy="8" r="5.5" stroke={PRIMER_COLORS.muted} strokeWidth="1.6" strokeDasharray="3 3" />
    </svg>
  );
}

/** 作业状态 → 图标（GitHub Actions 语义）。 */
export function JobStatusIcon({ status, conclusion }: { status: WorkflowJobStatus; conclusion: WorkflowConclusion | null }) {
  if (conclusion === 'skipped' || status === 'skipped') {
    return <SkippedIcon />;
  }
  if (conclusion === 'success') {
    return <SuccessIcon />;
  }
  if (conclusion === 'failure' || status === 'failed') {
    return <FailureIcon />;
  }
  if (status === 'running') {
    return <RunningIcon />;
  }
  return <PendingIcon />;
}

/** 运行状态 → 图标（运行级：任一 failure → 失败；running → 旋转）。 */
export function RunStatusIcon({ status, summary }: { status: WorkflowRunStatus; summary: { conclusion: string } | null }) {
  if (status === 'running' || status === 'pending') {
    return status === 'running' ? <RunningIcon size={18} /> : <PendingIcon size={18} />;
  }
  if (summary?.conclusion === 'success') {
    return <SuccessIcon size={18} />;
  }
  return <FailureIcon size={18} />;
}

/** 作业类型徽标（GitHub Actions 的 job 类型标识风格）。 */
export function JobTypeBadge({ jobType }: { jobType: 'rules' | 'simulation' }) {
  const isRules = jobType === 'rules';
  return (
    <span
      style={{
        fontSize: 11,
        lineHeight: '16px',
        padding: '0 6px',
        borderRadius: 8,
        border: `1px solid ${PRIMER_COLORS.border}`,
        color: PRIMER_COLORS.neutral,
        background: PRIMER_COLORS.canvas,
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
      }}
    >
      {isRules ? 'rules/check' : 'simulation/run'}
    </span>
  );
}
