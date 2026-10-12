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
export type ArtifactCategory = 'drawing' | 'model' | 'spec' | 'manual' | 'result';

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

/** 检查发现项（含规则与产物展示信息；迭代级发现项产物信息为空）。 */
export interface Finding {
  id: number;
  check_run_id: number;
  artifact_version_id: number | null;
  rule_item_id: number;
  severity: Severity;
  location: string;
  message: string;
  rule_code: string;
  rule_name: string;
  artifact_code: string | null;
  artifact_name: string | null;
  version_no: number | null;
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

/** 审查运行状态（waiting = 审批会签挂起，待人工签署后续跑）。 */
export type WorkflowRunStatus = 'pending' | 'running' | 'waiting' | 'succeeded' | 'failed';

/** 流水线作业状态（waiting = 审批作业等待人签）。 */
export type WorkflowJobStatus = 'pending' | 'running' | 'waiting' | 'succeeded' | 'failed' | 'skipped';

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

/** 流水线作业日志行（ts 为相对作业开始的秒数，旧行可缺省）。 */
export interface WorkflowJobLog {
  ts?: number;
  level: string;
  message: string;
}

/** 流水线步骤状态。 */
export type WorkflowStepStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped';

/** 流水线步骤（作业内平台内置执行环节）。 */
export interface WorkflowJobStep {
  id: number;
  job_id: number;
  step_key: string;
  name: string;
  status: WorkflowStepStatus;
  conclusion: WorkflowConclusion | null;
  order_index: number;
  logs: WorkflowJobLog[] | null;
  started_at: string | null;
  finished_at: string | null;
}

/** 流水线作业（含绑定展示字段与步骤序列）。 */
export interface WorkflowJob {
  id: number;
  run_id: number;
  job_key: string;
  name: string;
  job_type: 'rules' | 'simulation' | 'approval';
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
  steps: WorkflowJobStep[];
}

/** 运行汇总（结论与计数聚合）。 */
export interface WorkflowRunSummary {
  conclusion: WorkflowConclusion;
  jobs: { success: number; failure: number; skipped: number };
  findings: { error: number; warning: number; info: number };
  sims: { pass: number; fail: number };
}

/** 会签挂起摘要（运行 waiting 时的 summary 结构）。 */
export interface WorkflowWaitingSummary {
  status: 'waiting';
  awaiting_job_key: string;
  awaiting_job: string;
  awaiting_job_id: number;
}

/** 判定运行 summary 是否为会签挂起摘要。 */
export function isWaitingSummary(
  summary: WorkflowRunSummary | WorkflowWaitingSummary | null | undefined,
): summary is WorkflowWaitingSummary {
  return (
    summary !== null &&
    summary !== undefined &&
    'status' in summary &&
    (summary as { status?: string }).status === 'waiting'
  );
}

/** 运行触发方式（GitHub Actions 语义：push=方案提交，手动=manual，rerun=重新运行）。 */
export type WorkflowTrigger = 'submission' | 'manual' | 'rerun';

/** 审查运行（含作业概要）。 */
export interface WorkflowRun {
  id: number;
  iteration_id: number;
  workflow_id: number;
  workflow_code: string;
  definition: string;
  status: WorkflowRunStatus;
  summary: WorkflowRunSummary | WorkflowWaitingSummary | null;
  created_by: number | null;
  submission_id: number | null;
  trigger: WorkflowTrigger;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  task_id: number | null;
  submission_title: string;
  jobs: WorkflowJob[];
}

/** 提交迭代方案入参。 */
export interface SubmissionInput {
  title: string;
  note?: string;
}

/** 提交方案（触发事件：每个启用模板各产生一条运行）。 */
export interface IterationSubmission {
  id: number;
  iteration_id: number;
  title: string;
  note: string;
  submitted_by: number | null;
  created_at: string;
  runs: WorkflowRun[];
}

// ---- 审批会签（流水线内审批作业）----

/** 审批决定。 */
export type ApprovalDecision = 'approved' | 'rejected';

/** 审批签署入参。 */
export interface ApprovalInput {
  decision: ApprovalDecision;
  comment?: string;
}

/** 审批记录（单次签署）。 */
export interface ApprovalRecord {
  id: number;
  job_id: number;
  run_id: number;
  approver_id: number;
  approver_name: string;
  decision: ApprovalDecision;
  comment: string;
  created_at: string;
}

/** 待审批列表内嵌审批意见。 */
export interface ApprovalEntry {
  approver_name: string;
  decision: ApprovalDecision;
  comment: string;
  created_at: string;
}

/** 待审批作业（跨运行汇总，待办中心列表项）。 */
export interface PendingApproval {
  job_id: number;
  run_id: number;
  workflow_code: string;
  iteration_id: number;
  project_id: number;
  job_key: string;
  job_name: string;
  approvers: string[];
  min_count: number;
  approved_count: number;
  approvals: ApprovalEntry[];
  can_approve: boolean;
  created_at: string;
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
  manual: '技术说明书',
  result: '结果',
};

/** 产物审查状态（版本感知：最近一次检查运行结论）。 */
export type ReviewStatus = 'passed' | 'failed' | 'running' | 'unreviewed' | 'stale';

/** 审查状态中文标签映射。 */
export const REVIEW_STATUS_LABELS: Record<ReviewStatus, string> = {
  passed: '通过',
  failed: '未通过',
  running: '运行中',
  unreviewed: '未审查',
  stale: '已过期',
};

/** 项目审查状态聚合中的单条发现项（迭代级发现项产物信息为空）。 */
export interface ReviewFinding {
  id: number;
  check_run_id: number;
  artifact_version_id: number | null;
  version_no: number | null;
  rule_id: number;
  rule_code: string;
  rule_name: string;
  severity: Severity;
  location: string;
  message: string;
}

/** 项目级产物审查状态聚合项。 */
export interface ArtifactReviewStatus {
  artifact_id: number;
  code: string;
  name: string;
  category: ArtifactCategory;
  iteration_id: number;
  current_version_id: number | null;
  status: ReviewStatus;
  check_run_id: number | null;
  check_run_status: string | null;
  last_checked_at: string | null;
  last_check_started_at: string | null;
  findings: ReviewFinding[];
}

/** 项目级产物关联边（图样树构建用）。 */
export interface ProjectLink {
  id: number;
  src_artifact_id: number;
  dst_artifact_id: number;
  link_type: string;
}

/** 项目级审查运行列表项（跨迭代汇总）。 */
export interface ProjectRunItem {
  id: number;
  iteration_id: number;
  iteration_number: number;
  iteration_title: string;
  workflow_id: number;
  workflow_code: string;
  status: WorkflowRunStatus;
  summary: WorkflowRunSummary | null;
  trigger: WorkflowTrigger;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

// ---- 站内信通知 ----

/** 通知类型（域事件源标识）。 */
export type NotificationNType = 'run.completed' | 'approval.pending' | 'approval.recorded' | (string & {});

/** 站内信通知。 */
export interface NotificationItem {
  id: number;
  user_id: number;
  ntype: NotificationNType;
  title: string;
  body: string;
  project_id: number | null;
  link: string;
  resource_type: string;
  resource_id: string;
  read_at: string | null;
  created_at: string;
}

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

// ---- 迭代对比与审查报告 ----

/** 迭代简要信息（diff 双方标识）。 */
export interface IterationBrief {
  id: number;
  number: number;
  title: string;
  status: IterationStatus;
}

/** 字段级变更（产物编码或零件编码维度）。 */
export interface FieldChange {
  code?: string;
  part_code?: string;
  field: string;
  base: unknown;
  current: unknown;
}

/** 键控实体集合差异（产物 / BOM 通用）。 */
export interface EntryDiff {
  added: Record<string, unknown>[];
  removed: Record<string, unknown>[];
  changed: FieldChange[];
}

/** 检查发现项计数。 */
export interface SeverityCounts {
  error: number;
  warning: number;
  info: number;
}

/** 仿真结论快照。 */
export interface SimSnapshot {
  verdict: 'pass' | 'fail';
  failures: number;
}

/** 运行审批摘要。 */
export interface ApprovalSummary {
  approved: number;
  rejected: number;
  pending_jobs: number;
}

/** 迭代对比结果：产物 / BOM / 结论计数 / 仿真 / 审批五段差异。 */
export interface IterationDiff {
  iteration: IterationBrief;
  baseline: IterationBrief | null;
  note: string;
  artifacts: EntryDiff;
  bom: EntryDiff;
  findings: { baseline: SeverityCounts | null; current: SeverityCounts | null };
  sims: { baseline: SimSnapshot | null; current: SimSnapshot | null };
  approvals: { baseline: ApprovalSummary | null; current: ApprovalSummary | null };
}

/** 审查报告（Markdown 文本）。 */
export interface ReportData {
  iteration_id: number;
  generated_at: string;
  markdown: string;
}

/** 报告归档结果。 */
export interface ArchiveReportResult {
  artifact_id: number;
  artifact_code: string;
  version_no: number;
}

/** 仿真作业状态中文标签映射。 */
export const SIM_JOB_STATUS_LABELS: Record<SimJobStatus, string> = {
  pending: '排队中',
  running: '求解中',
  succeeded: '已完成',
  failed: '失败',
};

/** 审批决定中文标签映射。 */
export const APPROVAL_DECISION_LABELS: Record<ApprovalDecision, string> = {
  approved: '通过',
  rejected: '驳回',
};
