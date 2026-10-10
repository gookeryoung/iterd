/** 项目 / 成员 / 迭代 / 基线相关 API。 */

import { api } from './client';
import type {
  Baseline,
  BaselineDetail,
  Iteration,
  IterationInput,
  IterationStatus,
  Member,
  MemberRole,
  Project,
  ProjectInput,
  User,
} from '../types';
import { fetchUsers } from './auth';

export { fetchUsers };
export type { User };

/** 项目列表。 */
export async function fetchProjects(): Promise<Project[]> {
  const resp = await api.get<Project[]>('/projects');
  return resp.data;
}

/** 项目详情。 */
export async function fetchProject(id: number): Promise<Project> {
  const resp = await api.get<Project>(`/projects/${id}`);
  return resp.data;
}

/** 创建项目（后端 201）。 */
export async function createProject(data: ProjectInput): Promise<Project> {
  const resp = await api.post<Project>('/projects', data);
  return resp.data;
}

/** 项目成员列表。 */
export async function fetchMembers(projectId: number): Promise<Member[]> {
  const resp = await api.get<Member[]>(`/projects/${projectId}/members`);
  return resp.data;
}

/** 添加/更新成员。 */
export async function upsertMember(
  projectId: number,
  data: { user_id: number; role: MemberRole },
): Promise<Member> {
  const resp = await api.put<Member>(`/projects/${projectId}/members`, data);
  return resp.data;
}

/** 项目下迭代列表。 */
export async function fetchIterations(projectId: number): Promise<Iteration[]> {
  const resp = await api.get<Iteration[]>(`/projects/${projectId}/iterations`);
  return resp.data;
}

/** 创建迭代（number 自动自增，初始 planned）。 */
export async function createIteration(
  projectId: number,
  data: IterationInput,
): Promise<Iteration> {
  const resp = await api.post<Iteration>(`/projects/${projectId}/iterations`, data);
  return resp.data;
}

/** 迭代详情。 */
export async function fetchIteration(id: number): Promise<Iteration> {
  const resp = await api.get<Iteration>(`/iterations/${id}`);
  return resp.data;
}

/** 更新迭代（含状态迁移，非法迁移后端返回 400）。 */
export async function updateIteration(
  id: number,
  fields: { status?: IterationStatus; title?: string; objective?: string },
): Promise<Iteration> {
  const resp = await api.patch<Iteration>(`/iterations/${id}`, fields);
  return resp.data;
}

/** 迭代下基线列表。 */
export async function fetchBaselines(iterationId: number): Promise<Baseline[]> {
  const resp = await api.get<Baseline[]>(`/iterations/${iterationId}/baselines`);
  return resp.data;
}

/** 建立基线（planned 迭代后端返回 400）。 */
export async function createBaseline(iterationId: number, name: string): Promise<BaselineDetail> {
  const resp = await api.post<BaselineDetail>(`/iterations/${iterationId}/baselines`, { name });
  return resp.data;
}

/** 基线详情（含快照条目）。 */
export async function fetchBaseline(id: number): Promise<BaselineDetail> {
  const resp = await api.get<BaselineDetail>(`/baselines/${id}`);
  return resp.data;
}
