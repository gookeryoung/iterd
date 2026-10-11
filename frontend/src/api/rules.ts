/** 规则库 / 规则集 / 检查运行 / 发现项相关 API。 */

import { api } from './client';
import type {
  CheckerInfo,
  CheckRun,
  Finding,
  RuleCategory,
  RuleInput,
  RuleItem,
  RuleSet,
  RuleSetDetail,
  RuleSetInput,
  Severity,
} from '../types';

/** 规则库列表（可按分类过滤）。 */
export async function fetchRules(category?: RuleCategory): Promise<RuleItem[]> {
  const resp = await api.get<RuleItem[]>('/rules', {
    params: category ? { category } : undefined,
  });
  return resp.data;
}

/** 创建规则（后端 201）。 */
export async function createRule(data: RuleInput): Promise<RuleItem> {
  const resp = await api.post<RuleItem>('/rules', data);
  return resp.data;
}

/** 更新规则（含启用/停用与参数）。 */
export async function updateRule(id: number, data: Partial<RuleInput>): Promise<RuleItem> {
  const resp = await api.patch<RuleItem>(`/rules/${id}`, data);
  return resp.data;
}

/** 已注册检查器清单。 */
export async function fetchCheckers(): Promise<CheckerInfo[]> {
  const resp = await api.get<CheckerInfo[]>('/checkers');
  return resp.data;
}

/** 规则集列表（可按项目过滤，含全局）。 */
export async function fetchRuleSets(projectId?: number): Promise<RuleSet[]> {
  const resp = await api.get<RuleSet[]>('/rule-sets', {
    params: projectId !== undefined ? { project_id: projectId } : undefined,
  });
  return resp.data;
}

/** 创建规则集（后端 201）。 */
export async function createRuleSet(data: RuleSetInput): Promise<RuleSet> {
  const resp = await api.post<RuleSet>('/rule-sets', data);
  return resp.data;
}

/** 规则集详情（含成员规则 id）。 */
export async function fetchRuleSet(id: number): Promise<RuleSetDetail> {
  const resp = await api.get<RuleSetDetail>(`/rule-sets/${id}`);
  return resp.data;
}

/** 向规则集批量添加规则。 */
export async function addRulesToSet(id: number, ruleIds: number[]): Promise<RuleSetDetail> {
  const resp = await api.post<RuleSetDetail>(`/rule-sets/${id}/rules`, { rule_ids: ruleIds });
  return resp.data;
}

/** 迭代下检查运行列表。 */
export async function fetchCheckRuns(iterationId: number): Promise<CheckRun[]> {
  const resp = await api.get<CheckRun[]>(`/iterations/${iterationId}/check-runs`);
  return resp.data;
}

/** 检查运行详情（轮询用）。 */
export async function fetchCheckRun(runId: number): Promise<CheckRun> {
  const resp = await api.get<CheckRun>(`/check-runs/${runId}`);
  return resp.data;
}

/** 发现项列表（支持严重级别过滤）。 */
export async function fetchFindings(
  runId: number,
  filters: { severity?: Severity } = {},
): Promise<Finding[]> {
  const resp = await api.get<Finding[]>(`/check-runs/${runId}/findings`, {
    params: filters.severity ? { severity: filters.severity } : undefined,
  });
  return resp.data;
}

/** 严重级别选项（表单/筛选用）。 */
export const SEVERITY_OPTIONS: { value: Severity; label: string }[] = [
  { value: 'error', label: '错误' },
  { value: 'warning', label: '警告' },
  { value: 'info', label: '提示' },
];

/** 规则分类选项（表单/筛选用）。 */
export const RULE_CATEGORY_OPTIONS: { value: RuleCategory; label: string }[] = [
  { value: 'drafting', label: '制图' },
  { value: 'tolerance', label: '公差' },
  { value: 'material', label: '材料' },
  { value: 'process', label: '工艺' },
];
