/** 后端 API 类型定义（与 FastAPI Pydantic schema 一一对应）。 */

/** 用户信息。 */
export interface User {
  id: number;
  uid: string;
  username: string;
  email: string;
  is_superuser: boolean;
  is_active: boolean;
}

/** 登录响应。 */
export interface LoginResult {
  access_token: string;
  token_type: string;
  user: User;
}

/** 项目成员角色。 */
export type MemberRole = 'viewer' | 'designer' | 'reviewer' | 'admin' | 'owner';

/** 项目。 */
export interface Project {
  id: number;
  uid: string;
  parent_id: number | null;
  code: string;
  name: string;
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
}

/** 项目创建/更新入参。 */
export interface ProjectInput {
  code: string;
  name: string;
  description?: string;
  parent_id?: number | null;
  status?: string;
}

/** 项目成员。 */
export interface Member {
  id: number;
  project_id: number;
  user_id: number;
  role: MemberRole;
  username: string;
}

/** 当前用户在项目内的角色与能力位。 */
export interface MyRole {
  project_id: number;
  user_id: number;
  role: MemberRole | null;
  is_superuser: boolean;
  can_manage: boolean;
  can_design: boolean;
  can_review: boolean;
}

/** 迭代状态（状态机：planned -> active -> closed）。 */
export type IterationStatus = 'planned' | 'active' | 'closed';

/** 迭代。 */
export interface Iteration {
  id: number;
  uid: string;
  project_id: number;
  number: number;
  title: string;
  objective: string;
  start_date: string | null;
  end_date: string | null;
  status: IterationStatus;
  created_at: string;
  updated_at: string;
}

/** 迭代创建入参。 */
export interface IterationInput {
  title: string;
  objective?: string;
  start_date?: string | null;
  end_date?: string | null;
}

/** 产物类别。 */
export type ArtifactCategory = 'drawing' | 'model' | 'spec' | 'result';

/** 产物。 */
export interface Artifact {
  id: number;
  uid: string;
  project_id: number;
  iteration_id: number;
  code: string;
  name: string;
  category: ArtifactCategory;
  description: string;
  current_version_id: number | null;
  created_at: string;
  updated_at: string;
}

/** 产物创建入参。 */
export interface ArtifactInput {
  code: string;
  name: string;
  category: ArtifactCategory;
  description?: string;
}

/** 产物更新入参（名称/描述/类别/元数据）。 */
export interface ArtifactUpdateInput {
  name?: string;
  description?: string;
  category?: ArtifactCategory;
  metadata?: Record<string, unknown> | null;
}

/** 产物关联类型。 */
export type LinkType = 'part_of' | 'refers_to' | 'derived_from';

/** 产物关联入参。 */
export interface ArtifactLinkInput {
  dst_artifact_id: number;
  link_type: LinkType;
}

/** 产物关联。 */
export interface ArtifactLink {
  id: number;
  src_artifact_id: number;
  dst_artifact_id: number;
  link_type: LinkType;
  src_code: string;
  src_name: string;
  dst_code: string;
  dst_name: string;
}

/** 产物版本。 */
export interface ArtifactVersion {
  id: number;
  uid: string;
  artifact_id: number;
  version_no: number;
  filename: string;
  content_type: string;
  size: number;
  sha256: string;
  metadata_json: Record<string, unknown> | null;
  uploaded_by: number | null;
  note: string;
  created_at: string;
}

/** 基线条目。 */
export interface BaselineItem {
  id: number;
  artifact_id: number;
  artifact_version_id: number;
}

/** 基线。 */
export interface Baseline {
  id: number;
  uid: string;
  iteration_id: number;
  name: string;
  created_by: number | null;
  created_at: string;
}

/** 基线详情（含快照条目）。 */
export interface BaselineDetail extends Baseline {
  items: BaselineItem[];
}

/** 规则分类。 */
export type RuleCategory = 'drafting' | 'tolerance' | 'material' | 'process';

/** 严重级别。 */
export type Severity = 'error' | 'warning' | 'info';

/** 规则条目。 */
export interface RuleItem {
  id: number;
  code: string;
  name: string;
  category: RuleCategory;
  checker_type: string;
  params: Record<string, unknown> | null;
  severity_default: Severity;
  enabled: boolean;
  description: string;
  created_at: string;
  updated_at: string;
}

/** 规则创建入参。 */
export interface RuleInput {
  code: string;
  name: string;
  category: RuleCategory;
  checker_type: string;
  params?: Record<string, unknown> | null;
  severity_default?: Severity;
  description?: string;
  enabled?: boolean;
}

/** 规则集。 */
export interface RuleSet {
  id: number;
  project_id: number | null;
  name: string;
  description: string;
  created_at: string;
}

/** 规则集详情（含成员规则 id）。 */
export interface RuleSetDetail extends RuleSet {
  rule_ids: number[];
}

/** 迭代规则集绑定。 */
export interface RuleSetBinding {
  iteration_id: number;
  rule_set_id: number | null;
}

/** 已注册检查器。 */
export interface CheckerInfo {
  checker_type: string;
  description: string;
}

/** 规则集创建入参。 */
export interface RuleSetInput {
  name: string;
  project_id?: number | null;
  rule_ids: number[];
}

/** 检查运行状态。 */
export type CheckRunStatus = 'pending' | 'running' | 'succeeded' | 'failed';

/** 检查运行。 */
export interface CheckRun {
  id: number;
  iteration_id: number;
  rule_set_id: number;
  status: CheckRunStatus;
  summary: CheckSummary | null;
  started_at: string | null;
  finished_at: string | null;
  task_id: number | null;
}

/** 检查汇总（后端聚合结构）。 */
export interface CheckSummary {
  error: number;
  warning: number;
  info: number;
  artifacts: number;
  rules: number;
}

/** 检查发现项（含规则与产物展示信息）。 */
export interface Finding {
  id: number;
  check_run_id: number;
  artifact_version_id: number;
  rule_item_id: number;
  severity: Severity;
  location: string;
  message: string;
  rule_code: string;
  rule_name: string;
  artifact_code: string;
  artifact_name: string;
  version_no: number;
}

/** 仿真作业状态（状态机：pending -> running -> succeeded/failed）。 */
export type SimJobStatus = 'pending' | 'running' | 'succeeded' | 'failed';

/** 仿真结论（按模板阈值评估）。 */
export type SimVerdict = 'pass' | 'fail';

/** 求解器输入参数规格。 */
export interface SolverInputSpec {
  key: string;
  label: string;
  unit: string;
  default: number | null;
  required: boolean;
}

/** 求解器输出指标规格。 */
export interface SolverMetricSpec {
  key: string;
  label: string;
  unit: string;
}

/** 已注册求解器清单项。 */
export interface SolverInfo {
  solver_type: string;
  description: string;
  inputs: SolverInputSpec[];
  metrics: SolverMetricSpec[];
}

/** 仿真模板。 */
export interface SimTemplate {
  id: number;
  project_id: number | null;
  code: string;
  name: string;
  solver_type: string;
  params: Record<string, unknown> | null;
  thresholds: Record<string, unknown> | null;
  description: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

/** 仿真模板创建入参。 */
export interface SimTemplateInput {
  code: string;
  name: string;
  solver_type: string;
  project_id?: number | null;
  params?: Record<string, unknown> | null;
  thresholds?: Record<string, unknown> | null;
  description?: string;
  enabled?: boolean;
}

/** 仿真模板更新入参（部分更新）。 */
export interface SimTemplateUpdateInput {
  name?: string;
  solver_type?: string;
  params?: Record<string, unknown> | null;
  thresholds?: Record<string, unknown> | null;
  description?: string;
  enabled?: boolean;
}

/** 仿真作业汇总（后端聚合结构）。 */
export interface SimSummary {
  metrics: number;
  failures: number;
  verdict: SimVerdict;
}

/** 仿真作业。 */
export interface SimJob {
  id: number;
  iteration_id: number;
  template_id: number;
  artifact_version_id: number | null;
  status: SimJobStatus;
  inputs: Record<string, unknown> | null;
  summary: SimSummary | null;
  error: string | null;
  created_by: number | null;
  started_at: string | null;
  finished_at: string | null;
  task_id: number | null;
  template_name: string;
  solver_type: string;
  artifact_code: string;
  version_no: number | null;
}

/** 仿真作业发起入参。 */
export interface SimJobInput {
  template_id: number;
  artifact_version_id?: number | null;
  inputs?: Record<string, number | string> | null;
}

/** 仿真结果逐项判定明细。 */
export interface SimResultDetail {
  key: string;
  label: string;
  value: number;
  unit: string;
  min: number | null;
  max: number | null;
  passed: boolean;
}

/** 仿真结果。 */
export interface SimResult {
  id: number;
  sim_job_id: number;
  metrics: Record<string, number> | null;
  verdict: SimVerdict;
  failures: number;
  detail: SimResultDetail[] | null;
  created_at: string;
}

/** 审计日志。 */
export interface AuditLog {
  id: number;
  actor_id: number | null;
  actor_name: string;
  action: string;
  resource_type: string;
  resource_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string;
  created_at: string;
}

// ---- 审查流水线（workflows）----

/** 审查运行状态。 */
export type WorkflowRunStatus = 'pending' | 'running' | 'succeeded' | 'failed';

/** 流水线作业状态。 */
export type WorkflowJobStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped';

/** 作业结论（GitHub Actions 语义）。 */
export type WorkflowConclusion = 'success' | 'failure' | 'skipped';

/** 解析后的作业定义（模板详情展示）。 */
export interface WorkflowJobDef {
  key: string;
  name: string;
  uses: string;
  needs: string[];
  with: Record<string, unknown>;
}

/** 审查模板（YAML 编排）。 */
export interface WorkflowTemplate {
  id: number;
  project_id: number | null;
  code: string;
  name: string;
  description: string;
  definition: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  jobs: WorkflowJobDef[];
}

/** 审查模板创建入参。 */
export interface WorkflowTemplateInput {
  code: string;
  name: string;
  description?: string;
  project_id?: number | null;
  definition: string;
  enabled?: boolean;
}

/** 审查模板更新入参（部分更新）。 */
export interface WorkflowTemplateUpdateInput {
  name?: string;
  description?: string;
  definition?: string;
  enabled?: boolean;
}

/** 流水线作业日志行。 */
export interface WorkflowJobLog {
  level: string;
  message: string;
}

/** 流水线作业（含绑定展示字段）。 */
export interface WorkflowJob {
  id: number;
  run_id: number;
  job_key: string;
  name: string;
  job_type: 'rules' | 'simulation';
  needs: string[] | null;
  config: Record<string, unknown> | null;
  status: WorkflowJobStatus;
  conclusion: WorkflowConclusion | null;
  check_run_id: number | null;
  sim_job_id: number | null;
  logs: WorkflowJobLog[] | null;
  order_index: number;
  started_at: string | null;
  finished_at: string | null;
  rule_set_name: string;
  template_code: string;
  template_name: string;
  solver_type: string;
  artifact_code: string;
  version_no: number | null;
}

/** 运行汇总（结论与计数聚合）。 */
export interface WorkflowRunSummary {
  conclusion: WorkflowConclusion;
  jobs: { success: number; failure: number; skipped: number };
  findings: { error: number; warning: number; info: number };
  sims: { pass: number; fail: number };
}

/** 审查运行（含作业概要）。 */
export interface WorkflowRun {
  id: number;
  iteration_id: number;
  workflow_id: number;
  workflow_code: string;
  definition: string;
  status: WorkflowRunStatus;
  summary: WorkflowRunSummary | null;
  created_by: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  task_id: number | null;
  jobs: WorkflowJob[];
}

/** 严重级别中文标签映射。 */
export const SEVERITY_LABELS: Record<Severity, string> = {
  error: '错误',
  warning: '警告',
  info: '提示',
};

/** 产物类别中文标签映射。 */
export const ARTIFACT_CATEGORY_LABELS: Record<ArtifactCategory, string> = {
  drawing: '图纸',
  model: '模型',
  spec: '规格',
  result: '结果',
};

/** 规则分类中文标签映射。 */
export const RULE_CATEGORY_LABELS: Record<RuleCategory, string> = {
  drafting: '制图',
  tolerance: '公差',
  material: '材料',
  process: '工艺',
};

/** 成员角色中文标签映射。 */
export const ROLE_LABELS: Record<MemberRole, string> = {
  viewer: '查看者',
  designer: '设计者',
  reviewer: '评审者',
  admin: '管理员',
  owner: '所有者',
};

/** 迭代状态中文标签映射。 */
export const ITERATION_STATUS_LABELS: Record<IterationStatus, string> = {
  planned: '已计划',
  active: '进行中',
  closed: '已关闭',
};

/** 仿真作业状态中文标签映射。 */
export const SIM_JOB_STATUS_LABELS: Record<SimJobStatus, string> = {
  pending: '排队中',
  running: '求解中',
  succeeded: '已完成',
  failed: '失败',
};
