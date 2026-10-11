/** 仿真模板 / 作业 / 结果相关 API。 */

import { api } from './client';
import type {
  SimJob,
  SimJobInput,
  SimResult,
  SimTemplate,
  SimTemplateInput,
  SimTemplateUpdateInput,
  SolverInfo,
} from '../types';

/** 已注册求解器清单（含输入/输出规格）。 */
export async function fetchSolvers(): Promise<SolverInfo[]> {
  const resp = await api.get<SolverInfo[]>('/solvers');
  return resp.data;
}

/** 仿真模板列表（可按项目过滤，含全局）。 */
export async function fetchSimTemplates(
  projectId?: number,
): Promise<SimTemplate[]> {
  const resp = await api.get<SimTemplate[]>('/sim-templates', {
    params: projectId !== undefined ? { project_id: projectId } : undefined,
  });
  return resp.data;
}

/** 仿真模板详情。 */
export async function fetchSimTemplate(id: number): Promise<SimTemplate> {
  const resp = await api.get<SimTemplate>(`/sim-templates/${id}`);
  return resp.data;
}

/** 创建仿真模板（后端 201）。 */
export async function createSimTemplate(
  data: SimTemplateInput,
): Promise<SimTemplate> {
  const resp = await api.post<SimTemplate>('/sim-templates', data);
  return resp.data;
}

/** 更新仿真模板（部分更新，后端 200）。 */
export async function updateSimTemplate(
  id: number,
  data: SimTemplateUpdateInput,
): Promise<SimTemplate> {
  const resp = await api.patch<SimTemplate>(`/sim-templates/${id}`, data);
  return resp.data;
}

/** 发起仿真作业（后端 202，返回待执行的作业）。 */
export async function createSimJob(
  iterationId: number,
  data: SimJobInput,
): Promise<SimJob> {
  const resp = await api.post<SimJob>(
    `/iterations/${iterationId}/sim-jobs`,
    data,
  );
  return resp.data;
}

/** 迭代下仿真作业列表。 */
export async function fetchSimJobs(iterationId: number): Promise<SimJob[]> {
  const resp = await api.get<SimJob[]>(`/iterations/${iterationId}/sim-jobs`);
  return resp.data;
}

/** 仿真作业详情（轮询用）。 */
export async function fetchSimJob(jobId: number): Promise<SimJob> {
  const resp = await api.get<SimJob>(`/sim-jobs/${jobId}`);
  return resp.data;
}

/** 仿真结果（含逐项阈值判定）。 */
export async function fetchSimResult(jobId: number): Promise<SimResult> {
  const resp = await api.get<SimResult>(`/sim-jobs/${jobId}/result`);
  return resp.data;
}
