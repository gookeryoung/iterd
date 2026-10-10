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
}

/** 项目成员。 */
export interface Member {
  id: number;
  project_id: number;
  user_id: number;
  role: MemberRole;
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
}

/** 规则集。 */
export interface RuleSet {
  id: number;
  project_id: number | null;
  name: string;
  description: string;
  created_at: string;
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
}

/** 检查汇总（后端聚合结构）。 */
export interface CheckSummary {
  error: number;
  warning: number;
  info: number;
  artifacts: number;
  rules: number;
}

/** 检查发现项。 */
export interface Finding {
  id: number;
  check_run_id: number;
  artifact_version_id: number;
  rule_item_id: number;
  severity: Severity;
  location: string;
  message: string;
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
