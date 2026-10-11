/** 审查流水线（workflows）相关 API：模板 / 运行 / rerun。 */

import { api } from './client';
import type {
  WorkflowRun,
  WorkflowTemplate,
  WorkflowTemplateInput,
  WorkflowTemplateUpdateInput,
} from '../types';

export type { WorkflowTemplateInput, WorkflowTemplateUpdateInput };

/** 模板列表（可按项目过滤，含全局）。 */
export async function fetchWorkflows(projectId?: number): Promise<WorkflowTemplate[]> {
  const resp = await api.get<WorkflowTemplate[]>('/workflows', {
    params: projectId !== undefined ? { project_id: projectId } : undefined,
  });
  return resp.data;
}

/** 模板详情（含解析后 jobs 结构）。 */
export async function fetchWorkflow(id: number): Promise<WorkflowTemplate> {
  const resp = await api.get<WorkflowTemplate>(`/workflows/${id}`);
  return resp.data;
}

/** 创建模板（后端 201，YAML 校验失败 422）。 */
export async function createWorkflow(data: WorkflowTemplateInput): Promise<WorkflowTemplate> {
  const resp = await api.post<WorkflowTemplate>('/workflows', data);
  return resp.data;
}

/** 更新模板（definition 变更时后端重新校验）。 */
export async function updateWorkflow(
  id: number,
  data: WorkflowTemplateUpdateInput,
): Promise<WorkflowTemplate> {
  const resp = await api.patch<WorkflowTemplate>(`/workflows/${id}`, data);
  return resp.data;
}

/** 发起审查运行（后端 202，worker 编排执行）。 */
export async function createWorkflowRun(
  iterationId: number,
  workflowId: number,
): Promise<WorkflowRun> {
  const resp = await api.post<WorkflowRun>(`/iterations/${iterationId}/workflow-runs`, {
    workflow_id: workflowId,
  });
  return resp.data;
}

/** 迭代下运行列表（含作业概要与任务 id）。 */
export async function fetchWorkflowRuns(iterationId: number): Promise<WorkflowRun[]> {
  const resp = await api.get<WorkflowRun[]>(`/iterations/${iterationId}/workflow-runs`);
  return resp.data;
}

/** 运行详情（含全部作业、日志与绑定信息；轮询用）。 */
export async function fetchWorkflowRun(runId: number): Promise<WorkflowRun> {
  const resp = await api.get<WorkflowRun>(`/workflow-runs/${runId}`);
  return resp.data;
}

/** 以运行快照重新执行（生成新 run）。 */
export async function rerunWorkflowRun(runId: number): Promise<WorkflowRun> {
  const resp = await api.post<WorkflowRun>(`/workflow-runs/${runId}/rerun`);
  return resp.data;
}
