/** 迭代对比与审查报告 API。 */

import { api } from './client';
import type { ArchiveReportResult, IterationDiff, ReportData } from '../types';

/** 迭代对比（baseline 缺省由后端自动选取前序 closed 迭代）。 */
export async function fetchIterationDiff(iterationId: number, baselineId?: number): Promise<IterationDiff> {
  const resp = await api.get<IterationDiff>(`/iterations/${iterationId}/diff`, {
    params: baselineId != null ? { baseline: baselineId } : {},
  });
  return resp.data;
}

/** 生成交付审查报告（Markdown，不落库）。 */
export async function fetchIterationReport(iterationId: number): Promise<ReportData> {
  const resp = await api.get<ReportData>(`/iterations/${iterationId}/report`);
  return resp.data;
}

/** 报告归档为 result 产物（designer+，可重复归档追加版本）。 */
export async function archiveIterationReport(iterationId: number): Promise<ArchiveReportResult> {
  const resp = await api.post<ArchiveReportResult>(`/iterations/${iterationId}/report/archive`);
  return resp.data;
}
