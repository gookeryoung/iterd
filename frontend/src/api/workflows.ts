/** 审查流水线（workflows）相关 API：模板 / 提交方案 / 运行 / rerun。 */

import { api } from './client';
import type {
  ApprovalInput,
  ApprovalRecord,
  IterationSubmission,
  PendingApproval,
  ProjectRunItem,
  SubmissionInput,
  WorkflowRun,
  WorkflowTemplate,
  WorkflowTemplateInput,
  WorkflowTemplateUpdateInput,
} from '../types';

export type { WorkflowTemplateInput, WorkflowTemplateUpdateInput };

/** 提交迭代方案（后端 202，为每个启用模板各产生一条运行）。 */
export async function createSubmission(
  iterationId: number,
  data: SubmissionInput,
): Promise<IterationSubmission> {
  const resp = await api.post<IterationSubmission>(
    `/iterations/${iterationId}/submissions`,
    data,
  );
  return resp.data;
}

/** 迭代下提交方案列表（含各自触发的运行）。 */
export async function fetchSubmissions(iterationId: number): Promise<IterationSubmission[]> {
  const resp = await api.get<IterationSubmission[]>(`/iterations/${iterationId}/submissions`);
  return resp.data;
}

/** 提交方案详情。 */
export async function fetchSubmission(id: number): Promise<IterationSubmission> {
  const resp = await api.get<IterationSubmission>(`/submissions/${id}`);
  return resp.data;
}

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

/** 项目级运行列表（跨迭代汇总，按 id 倒序）。 */
export async function fetchProjectRuns(projectId: number): Promise<ProjectRunItem[]> {
  const resp = await api.get<ProjectRunItem[]>(`/projects/${projectId}/workflow-runs`);
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

/** 待审批作业列表（跨运行汇总；project_id 过滤可选）。 */
export async function fetchPendingApprovals(projectId?: number): Promise<PendingApproval[]> {
  const resp = await api.get<PendingApproval[]>('/approvals/pending', {
    params: projectId !== undefined ? { project_id: projectId } : undefined,
  });
  return resp.data;
}

/** 作业的审批记录（按 id 升序）。 */
export async function fetchJobApprovals(jobId: number): Promise<ApprovalRecord[]> {
  const resp = await api.get<ApprovalRecord[]>(`/workflow-jobs/${jobId}/approvals`);
  return resp.data;
}

/** 签署审批意见（达成会签条件时后端同步续跑流水线）。 */
export async function recordApproval(jobId: number, data: ApprovalInput): Promise<ApprovalRecord> {
  const resp = await api.post<ApprovalRecord>(`/workflow-jobs/${jobId}/approvals`, data);
  return resp.data;
}
