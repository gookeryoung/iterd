/**
 * MSW 测试网络层 —— 组件测试统一走 service worker 拦截，
 * 与真实后端解耦；onUnhandledRequest: 'error' 确保漏配端点在测试中显式报错.
 *
 * 用法：默认 handlers 覆盖组件测试常用端点（auth / projects / rules /
 * workflows / audit）；单用例可 server.use() 覆盖.
 */

import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import type {
  AuditLog,
  CheckerInfo,
  Project,
  RuleItem,
  RuleSet,
  User,
  WorkflowTemplate,
} from '../types'

// ─────────────── 测试 fixtures ───────────────

export const mockUser: User = {
  id: 1,
  uid: 'u-admin',
  username: 'admin',
  email: 'admin@example.com',
  is_superuser: true,
  is_active: true,
}

export const mockProject: Project = {
  id: 10,
  uid: 'p-demo',
  parent_id: null,
  code: 'DEMO',
  name: '演示项目',
  description: 'MSW 默认项目',
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

export const mockRule: RuleItem = {
  id: 100,
  code: 'DRW-001',
  name: '图层命名规范',
  category: 'drafting',
  checker_type: 'convention.filename',
  params: null,
  severity_default: 'warning',
  enabled: true,
  description: '图纸文件命名需符合规范',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

export const mockRuleSet: RuleSet = {
  id: 200,
  project_id: null,
  name: '演示规则集',
  description: 'MSW 默认规则集',
  created_at: '2026-01-01T00:00:00Z',
}

export const mockChecker: CheckerInfo = {
  checker_type: 'convention.filename',
  description: '文件命名规范检查',
}

export const mockWorkflow: WorkflowTemplate = {
  id: 300,
  project_id: null,
  code: 'DEMO-REVIEW',
  name: '演示审查流水线',
  description: 'MSW 默认模板',
  definition: 'jobs:\n  check:\n    uses: rules/check\n',
  enabled: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  jobs: [{ key: 'check', name: '规则检查', uses: 'rules/check', needs: [], with: {} }],
}

export const mockAuditLog: AuditLog = {
  id: 1,
  actor_id: 1,
  actor_name: 'admin',
  action: 'login',
  resource_type: 'auth',
  resource_id: '1',
  before: null,
  after: null,
  ip: '127.0.0.1',
  created_at: '2026-01-01T00:00:00Z',
}

// ─────────────── 默认 handlers ───────────────

export const handlers = [
  // 认证
  http.post('/api/v1/auth/login', () =>
    HttpResponse.json({
      access_token: 'fake-token',
      token_type: 'bearer',
      user: mockUser,
    })),
  http.get('/api/v1/auth/me', () => HttpResponse.json(mockUser)),
  http.get('/api/v1/users', () => HttpResponse.json([mockUser])),

  // 项目
  http.get('/api/v1/projects', () => HttpResponse.json([mockProject])),
  http.get('/api/v1/projects/:id', () => HttpResponse.json(mockProject)),
  http.get('/api/v1/projects/:id/members', () => HttpResponse.json([])),
  http.get('/api/v1/projects/:id/me', () =>
    HttpResponse.json({
      project_id: 10,
      user_id: 1,
      role: 'owner',
      is_superuser: true,
      can_manage: true,
      can_design: true,
      can_review: true,
    })),
  http.get('/api/v1/projects/:id/iterations', () => HttpResponse.json([])),
  http.get('/api/v1/projects/:id/workflow-runs', () => HttpResponse.json([])),

  // 迭代
  http.get('/api/v1/iterations/:id', () =>
    HttpResponse.json({
      id: 1,
      uid: 'i-1',
      project_id: 10,
      number: 1,
      title: '演示迭代',
      objective: '',
      start_date: null,
      end_date: null,
      status: 'active',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    })),

  // 产物
  http.get('/api/v1/artifacts', () => HttpResponse.json([])),

  // 规则库
  http.get('/api/v1/rules', () => HttpResponse.json([mockRule])),
  http.get('/api/v1/checkers', () => HttpResponse.json([mockChecker])),
  http.get('/api/v1/rule-sets', () => HttpResponse.json([mockRuleSet])),

  // 审查流水线
  http.get('/api/v1/workflows', () => HttpResponse.json([mockWorkflow])),

  // 审计日志
  http.get('/api/v1/audit-logs', () => HttpResponse.json([mockAuditLog])),
]

export const server = setupServer(...handlers)
