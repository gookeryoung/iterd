/** 通用状态/枚举标签渲染组件。 */

import { Tag } from 'antd';
import {
  ARTIFACT_CATEGORY_LABELS,
  ITERATION_STATUS_LABELS,
  REVIEW_STATUS_LABELS,
  SEVERITY_LABELS,
  type ArtifactCategory,
  type IterationStatus,
  type ReviewStatus,
  type Severity,
} from '../types';

/** 严重级别标签：error 红 / warning 橙 / info 蓝。 */
export function SeverityTag({ severity }: { severity: Severity }) {
  const color = severity === 'error' ? 'red' : severity === 'warning' ? 'orange' : 'blue';
  return <Tag color={color}>{SEVERITY_LABELS[severity]}</Tag>;
}

/** 迭代状态标签。 */
export function IterationStatusTag({ status }: { status: IterationStatus }) {
  const color = status === 'active' ? 'green' : status === 'planned' ? 'default' : 'gray';
  return <Tag color={color}>{ITERATION_STATUS_LABELS[status]}</Tag>;
}

/** 产物类别标签。 */
export function CategoryTag({ category }: { category: ArtifactCategory }) {
  return <Tag>{ARTIFACT_CATEGORY_LABELS[category] ?? category}</Tag>;
}

/** 审查状态标签：passed 绿 / failed 红 / running 蓝 / unreviewed 灰 / stale 橙。 */
export function ReviewStatusTag({ status }: { status: ReviewStatus }) {
  const colorMap: Record<ReviewStatus, string> = {
    passed: 'green',
    failed: 'red',
    running: 'blue',
    unreviewed: 'default',
    stale: 'orange',
  };
  return <Tag color={colorMap[status]}>{REVIEW_STATUS_LABELS[status]}</Tag>;
}
