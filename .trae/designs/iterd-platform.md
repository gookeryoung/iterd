# IterD 平台开发方案

对应需求：`.trae/req/req-01-iterd-platform.md`。
工程底座：复用 F:\Dev\cndb 已验证的插件化 FastAPI 架构、CLI 体系、前端框架与工具链。

## 1. 总体架构决策

需求说明按企业级中台配置选型（Celery+Redis、MinIO、Neo4j、K8s），本项目为个人项目，按"单机可部署、零外部依赖起步、协议留扩展"原则裁剪。对照如下：

| 需求说明选型 | 本方案选型 | 理由 |
|---|---|---|
| Celery + Redis/MQ | 任务表 + 内置 worker 进程（`iterd worker`） | 符合本项目 webdev 规则"长任务用任务表模式"；cndb 异步导入已验证 DB 解耦模式；Redis 属重运维依赖。执行层抽象为协议，P3 可换 Celery 实现而不动业务代码 |
| SQLModel | SQLAlchemy 2.0 + Pydantic v2 分层 | 与 webdev 规则一致；SQLModel 类型生态与 pyrefly 配合弱；cndb 已有成熟分层样板 |
| PostgreSQL | SQLite 默认 / PostgreSQL 可选（`ITERD_DATABASE_URL`） | cndb 模式：开发零配置，生产同一切换 |
| MinIO（S3） | `StorageBackend` 协议：local 默认（内容寻址）/ s3 P1 可选 | MVP 零外部依赖；协议对齐 boto3 接口子集，切换 MinIO 仅换实现 |
| Neo4j（数字线程） | 关联表 + 递归 CTE（WITH RECURSIVE） | SQLite/PG 均支持；追溯深度 ≤ 5 跳场景性能足够；P3 数据量上来再评估图库 |
| Nginx/Traefik 网关 | FastAPI 同源托管 SPA（cndb app.py 模式） | 单容器即可上线；需要 gzip/SSL 时复用 cndb 双容器 compose 方案 |
| K8s/Slurm（仿真） | 本地进程执行器；`SolverAdapter` 协议预留远程执行 | 单机先行；协议含 submit/poll，天然支持后续容器/HPC 实现 |
| React Flow | 沿用（P2 数字线程可视化） | 与 AntD 生态兼容 |

待用户复核：是否沿用 cndb 的 Win7 兼容依赖上界（pydantic<2.7、fastapi<0.126、pydantic-settings<2.3、bcrypt<4、cryptography 42.x）。本方案默认沿用（假定部署环境与 cndb 一致）；若 IterD 仅部署在现代环境，可放宽至最新版并移除相关上界。

## 2. cndb 资产复用清单

| 资产 | 来源 | 复用方式 |
|---|---|---|
| 后端骨架 | `src/cndb/{core,api,models,app.py}` | 移植：config（pydantic-settings + `ITERD_` 前缀）、database（engine/会话/读写分离）、errors（业务异常基类 + 统一 `{"detail","code"}` 契约）、migrations（lifespan 自动 alembic）、plugin_registry（自动发现挂载）、security（JWT/bcrypt）、system_api |
| 插件三层模式 | `plugins/workspaces/*` | 每个领域插件：`plugin.py`（注册）+ `models.py` + `routers/` + `schemas/` + `services/`，路由层禁止 ORM |
| CLI 体系 | `cli/*` | 移植 serve/dev/build/info/seed/backup/restore/users，新增 worker |
| 前端框架 | `frontend/*` | 移植 Vite6 + React18 + TS strict + AntD5 + React Query5 + zustand5 + vitest + playwright + bundle-budget；布局/主题/请求封装/登录页 |
| 工具链 | Makefile + ruff + pyrefly + pytest | 原样移植，`make check` = lint + typecheck + frontend-check + cov(95%) 并行 |
| 部署 | Dockerfile + compose + fspack | 移植 wheel 单容器方案；fspack 打包桌面分发 |
| 备份恢复 | `cli/backup.py` | 移植，归档 DB + 对象存储目录 |

不移植：cndb 的动态表/字段引擎（tables 插件）、GUI 面板（cndbw）、Jinja2 报告（IterD 有自己的报告体系）。

## 3. 代码结构

```
src/iterd/
├── api/                    # 认证依赖 get_current_user、公共依赖
├── core/                   # config / database / errors / migrations
│   │                       # plugin_registry / security / system_api
│   ├── storage/            # StorageBackend 协议 + local/s3 实现
│   └── events/             # 进程内事件总线（asyncio pub/sub）
├── models/                 # SQLAlchemy Base + 公共 mixin
├── plugins/
│   ├── accounts/           # 用户/JWT/API Token（从 cndb 移植）
│   ├── projects/           # 项目树/迭代/基线/项目成员 RBAC
│   ├── artifacts/          # 设计产物/版本/元数据/关联/预览
│   ├── rules/              # 规则库/规则集/检查任务/报告
│   ├── simulation/         # 仿真模板/任务/结果/评估
│   ├── changes/            # ECR/ECN/评审
│   ├── trace/              # 溯源注册/关联图/追溯查询
│   └── notify/             # 通知/Webhook/审计
├── tasks/                  # 任务执行框架（跨插件共用）
│   ├── models.py           # task 表 + 状态机
│   ├── worker.py           # iterd worker 主循环
│   └── executor.py         # TaskExecutor 协议 + 注册表
├── checkers/               # 内置规则检查器（CheckerAdapter 实现）
├── solvers/                # 求解器适配器（SolverAdapter 实现，P1）
├── cli/                    # iterd serve/dev/worker/seed/backup/...
├── alembic/                # 迁移脚本
├── app.py                  # FastAPI 装配 + SPA 托管 + WebSocket
└── static/                 # 前端构建产物

frontend/src/
├── api/                    # axios 封装 + React Query hooks
├── components/             # 通用组件
├── pages/
│   ├── auth/  admin/       # 移植 cndb
│   ├── projects/           # 项目列表/详情（迭代列表+看板）
│   ├── iterations/         # 迭代详情（产物/规则/仿真/变更 Tab）
│   ├── artifacts/          # 设计工作台：上传/版本/预览/关联
│   ├── rules/              # 规则库/规则集/检查报告
│   ├── simulation/         # 仿真控制台（P1）
│   ├── changes/            # ECR/ECN/评审（P2）
│   └── trace/              # 数字线程图谱 React Flow（P2）
├── store/  hooks/  types/  # zustand / WebSocket hooks / 接口类型
└── layouts/  theme/  utils/
```

## 4. 数据模型

公共约定：主键 `id` 为 int 自增；对外暴露的实体额外生成 UUID `uid`；所有表含 `created_at`/`updated_at`；不物理删除业务主数据（软删 `deleted_at`），审计与任务表只增不改。

### accounts（移植 cndb）
- `users`：id, username, email, hashed_password, is_superuser, is_active
- `api_tokens`：id, user_id, name, token_hash(SHA-256), last_used_at

### projects
- `projects`：id, parent_id(自关联，多级), code, name, description, status
- `project_members`：project_id, user_id, role（viewer/designer/reviewer/admin/owner）
- `iterations`：id, project_id, number(迭代编号，项目内唯一), title, objective, start_date, end_date, status（planned/active/closed）
- `baselines`：id, iteration_id, name, created_by, created_at
- `baseline_items`：baseline_id, artifact_id, artifact_version_id（版本快照，建立后不受后续上传影响）

### artifacts
- `artifacts`：id, project_id, iteration_id, code, name, category（drawing/model/spec/result）, description, current_version_id
- `artifact_versions`：id, artifact_id, version_no, filename, content_type, size, sha256, storage_key, metadata(JSON，材料/尺寸/公差等), uploaded_by, note
- `artifact_links`：id, src_artifact_id, dst_artifact_id, link_type（part_of/refers_to/derived_from）

### rules
- `rule_items`：id, code, name, category（drafting/tolerance/material/process）, checker_type, params(JSON，检查器参数), severity_default, enabled
- `rule_sets`：id, project_id(可空=全局), name, description
- `rule_set_items`：rule_set_id, rule_item_id
- `rule_set_bindings`：rule_set_id, project_id/iteration_id（P0 绑定迭代）
- `check_runs`：id, iteration_id, rule_set_id, status（pending/running/succeeded/failed）, started_at, finished_at, summary(JSON：错误/警告/提示计数)
- `check_findings`：id, check_run_id, artifact_version_id, rule_item_id, severity（error/warning/info）, location, message

### simulation（P1）
- `sim_templates`：id, project_id, solver_type, name, input_pattern, params_schema(JSON), criteria(JSON：指标/比较符/目标值)
- `sim_jobs`：id, iteration_id, template_id, artifact_version_id, status, priority, workdir, submitted_at, started_at, finished_at
- `sim_results`：id, sim_job_id, metrics(JSON：标准化指标), passed, deviations(JSON), result_file_key, thumbnail_key

### changes（P2）
- `ecrs`：id, project_id, origin, problem_desc, impact_scope, proposal, status
- `ecns`：id, ecr_id, code, status, approved_by, approved_at
- `ecn_items`：ecn_id, artifact_id, action
- `reviews`：id, target_type/target_id（迭代/ECR），reviewer_ids, status, conclusion
- `review_comments`：review_id, author_id, body, created_at

### trace
- `trace_nodes`：urn(主键，`urn:iterd:{type}:{uuid}`), node_type（project/iteration/artifact_version/rule_item/check_finding/sim_result/ecr/review/baseline）, display_name, ref_table, ref_id
- `trace_links`：id, src_urn, dst_urn, link_type（contains/derives_from/validated_by/affected_by/approved_by）

### notify
- `audit_logs`：id, actor_id, action, resource_type, resource_id, before(JSON), after(JSON), ip, created_at
- `notifications`：id, user_id, event_type, payload(JSON), read_at
- `webhooks` + `webhook_deliveries`（P1）

### tasks（任务执行框架，跨插件）
- `tasks`：id, task_type（check_run/sim_job）, payload(JSON), status（pending/running/succeeded/failed/cancelled）, priority, worker_id, heartbeat_at, attempts, max_attempts, error, created_at, started_at, finished_at

## 5. 核心模块设计

### 5.1 任务执行框架（规则检查与仿真共用）

接口定义：

```python
class TaskExecutor(Protocol):
    """任务执行器协议，按 task_type 注册到执行器注册表."""

    task_type: str

    async def execute(self, payload: dict[str, Any], ctx: TaskContext) -> TaskResult:
        """执行任务；ctx 提供 progress(stage, percent) 回调与 storage/db 句柄."""


class TaskContext(Protocol):
    def progress(self, stage: str, percent: int) -> None: ...
    def log(self, level: str, message: str) -> None: ...
```

执行流程（状态机）：

1. API 创建业务对象（check_run/sim_job）+ `tasks` 记录（同事务，status=pending）。
2. worker 进程（`iterd worker`，可多实例）主循环：事务内抢占（`UPDATE ... SET status='running', worker_id=? WHERE id=(SELECT ... WHERE status='pending' ORDER BY priority, id LIMIT 1) RETURNING *`，SQLite 用 `BEGIN IMMEDIATE` 串行化抢占）。
3. 执行器回调 `ctx.progress` 更新 tasks.progress 与业务表，日志写 `task` 内嵌 JSON 字段。
4. 结束回写 succeeded/failed；失败且 attempts < max_attempts(3) 退避后重回 pending。
5. 心跳：running 状态每 10s 更新 heartbeat_at；启动时与周期扫描将心跳超时(60s)的 running 任务判失败（attempts+1）。
6. WebSocket `/ws/tasks/{task_id}` 推送进度与日志；API 进程与 worker 通过 DB 解耦，无进程间直连。

幂等性：执行器必须支持重复执行——check_run 重跑先清空自身 findings 再写入；sim_job 重跑使用独立 workdir（`data/sim/{job_id}/attempt_{n}/`）。

### 5.2 规则检查引擎

检查器协议：

```python
class CheckerAdapter(Protocol):
    """静态规则检查器协议，按 checker_type 注册，新增检查器不改平台代码."""

    checker_type: str

    def supported_extensions(self) -> tuple[str, ...]: ...

    def check(self, artifact: ArtifactRef, rules: list[RuleRef], ctx: CheckerContext) -> list[Finding]: ...
```

P0 内置检查器（可测、无 CAD 解析依赖）：
- `filename_convention`：按规则 params 的正则/命名模板校验产物文件名与编码。
- `metadata_required`：校验 metadata JSON 必填键（材料/尺寸/公差）与类型。
- `spec_markdown_lint`（P1）：技术规范 Markdown 的标题层级/必填章节校验。

检查流程：迭代详情页发起 → 选择规则集 → 创建 check_run + task → worker 按产物×规则分发到检查器池（进程内并发，`asyncio.gather` + 信号量限 4）→ findings 聚合入库 → summary 计数 → WebSocket 通知 → 报告页按产物/严重级别/规则过滤展示。

历史对比（P1）：取同 artifact 相邻两次 check_run 的 findings，按 (rule_item_id, location) 对齐，输出新增/修复/持续三类差异与错误数趋势。

### 5.3 仿真验证（P1）

求解器适配器协议：

```python
class SolverAdapter(Protocol):
    """求解器适配器，屏蔽 FEM/CFD/多体动力学差异，按 solver_type 注册."""

    solver_type: str

    def prepare(self, job: SimJobRef, storage: StorageBackend) -> str:
        ...
        # 下载输入产物到 workdir，按模板 params 渲染求解配置，返回 workdir

    def submit(self, workdir: str) -> str:
        ...
        # 启动求解（本地子进程；远程实现提交后返回句柄），返回 handle

    def poll(self, handle: str) -> SimPollResult:
        ...
        # running / succeeded / failed + 进度

    def collect(self, workdir: str) -> SimResultBundle:
        ...
        # 解析输出为标准化指标 metrics + 云图缩略图，上传存储
```

P1 交付 `mock_solver`（按参数生成正弦位移场 CSV + 指标，sleep 模拟耗时），验证全链路；真实求解器按协议逐个接入。
自动评估：`criteria` 形如 `[{"metric": "max_displacement", "op": "<=", "target": 2.0}]`，逐条比对输出 passed 与偏差量；与上一版本同名指标对比输出趋势。

### 5.4 设计产物与存储

`StorageBackend` 协议：`put(key, stream) -> StorageObject(size, sha256)` / `open(key)` / `delete(key)` / `exists(key)` / `url(key, expires)`。

local 实现：内容寻址 `data/objects/{sha256[:2]}/{sha256}`，天然去重、版本不可变。上传即计算 sha256，同内容版本共享存储对象；`artifact_versions.storage_key` 指向该对象。

版本规则：每次上传生成新 version_no（递增），旧版本不可修改仅可查看/下载；`artifacts.current_version_id` 指向最新。预览：P0 生成通用文件卡片（类型图标+大小+版本），Markdown 用前端渲染，图片直出；DWG/STEP 缩略图 P2（依赖解析器，标注为可选增强）。

元数据：P0 表单录入 + `metadata` JSON 自由扩展；P1 接入解析器（DXF 用 ezdxf、STEP 用 steputils，按需评估）自动回填，人工值优先。

### 5.5 数字线程

注册时机：与业务写操作同事务调用 `trace.register(node_type, ref_table, ref_id, display_name)` 生成 URN；关联动作（产物关联/检查执行/仿真完成/ECN 影响标记/基线建立）调用 `trace.link(src, dst, link_type)`。

追溯查询：`GET /api/v1/trace/graph?urn=...&direction=up|down|both&depth=N`，SQL 用 `WITH RECURSIVE` 展开 trace_links，联表取 display_name，返回节点+边（DAG 结构，按 urn 去重防环）。前端 React Flow 分层布局渲染（P2）。

### 5.6 通知与审计

- 事件总线：`core/events` 进程内 asyncio pub/sub；关键动作（迭代关闭/检查完成/仿真完成/评审通过）由服务层发布。API 进程内消费者：写 notifications + WebSocket 推送 + webhook 投递（P1，3 次指数退避重试）。
- 审计：服务层写操作统一调用 `audit(actor, action, resource, before, after)`，与业务同事务；audit_logs 无 UPDATE/DELETE 路径，API 层不提供修改接口。
- WebSocket：`/ws/notifications`（按 user_id 定向）、`/ws/tasks/{task_id}`（进度/日志流）。

### 5.7 RBAC

项目级五角色（复用 cndb 权限校验模式）：

| 角色 | 权限 |
|---|---|
| viewer | 只读 |
| designer | 上传产物、发起检查/仿真、创建 ECR |
| reviewer | viewer + 评审操作、批准基线/ECN |
| admin | 项目内全部管理（成员/规则集/迭代） |
| owner | admin + 删除项目/转让 |

实现：`require_project_role(min_role)` 依赖注入，按 project_id 校验 project_members；迭代级权限 P2 再叠加。

## 6. 异常处理与错误码

复用 cndb 错误契约：业务异常 `IterdError(status_code, code, detail, context)` → 统一响应 `{"detail", "code"}`，app.py 全局 handler 映射，路由层禁止裸 500。

错误码段（前缀 `ITERD-`）：
- 400 业务校验：`INVALID_STATE`（状态机非法迁移）、`DUPLICATE_CODE`、`BASELINE_LOCKED`（基线后禁止的操作）
- 403：`PERMISSION_DENIED`（含越权访问非成员项目）
- 404：`NOT_FOUND`（统一资源不存在）
- 409：`VERSION_CONFLICT`（并发上传同产物）
- 422：`CHECKER_ERROR` / `SOLVER_ERROR`（适配器执行失败明细）
- 任务级错误写 tasks.error 并映射到报告页，不抛给 API。

## 7. 分期交付计划

### P0（MVP）—— 3 轮迭代

**迭代 1：底座移植 + 项目迭代**
- 移植 cndb 骨架（core/api/models/app.py/CLI/accounts 插件/Makefile/Dockerfile/前端骨架），全局改名 cndb→iterd，配置前缀 `ITERD_`
- projects 插件：项目树/迭代 CRUD+状态机/项目成员 RBAC + 前端项目列表/详情页
- notify 插件（审计部分）+ alembic 初始迁移 + seed 演示数据
- 验收：登录→建项目→建迭代→加成员，审计可查

**迭代 2：设计产物管理**
- core/storage（local 内容寻址）+ artifacts 插件：上传/下载/版本列表/软删/元数据/产物关联/基础预览
- 基线：建立基线锁版本快照
- 前端设计工作台（上传/版本抽屉/关联管理）
- 验收：多版本上传回溯、基线锁定后不受新上传影响

**迭代 3：规则检查 MVP + 收尾**
- tasks 框架（任务表+worker+心跳+重试+WebSocket 进度）+ `iterd worker` CLI
- rules 插件：规则库/规则集/绑定/批量检查 + filename_convention、metadata_required 检查器 + 报告页
- trace URN 注册随各业务动作接入
- Docker compose（app+worker 双进程）
- 验收：req-01 第 9 节 P0 验收标准全过

### P1 —— 2 轮迭代
- 仿真全链路（模板/任务/mock 求解器/结果标准化/自动评估/控制台页面）
- 检查历史对比（findings 对齐 + 趋势）+ 通知（站内信/WebSocket/Webhook）
- 元数据自动解析（DXF 优先）

### P2 —— 2~3 轮迭代
- ECR/ECN + 评审流程 + 变更追溯；多规则集管理
- trace_links 完整接入 + 追溯查询 API + React Flow 图谱页
- 检查器独立部署模式（子进程适配器）

### P3 —— 按需
- 真实求解器接入（FEM/CFD 各一）+ 远程执行器（容器/HPC）
- Neo4j 评估、性能优化、SSO

## 8. 依赖项与约束

- 外部依赖（P0）：无（SQLite + 本地存储 + 进程内 worker）。
- 新增 Python 依赖（P0）：`python-multipart`（上传）、`fastapi-offline`、`bcrypt`/`python-jose`/`cryptography`（随 cndb 移植）。P1 视需要加 `ezdxf`（DXF 解析）、`boto3`（S3 可选）。
- 数据格式版本：备份归档格式沿用 cndb tar.gz 结构，含 DB + `data/objects/`，`backup_format_version=2`（iterd 起算，与 cndb 不兼容互恢复）。
- 不变量：artifact_versions 不可变（无 UPDATE 路径）；baseline_items 建立后不变；trace_nodes.urn 全局唯一；tasks 状态机单向（failed→pending 重试除外）。
- 前后端契约：FastAPI 为类型真理源，Pydantic schema 变更同步 `frontend/src/types/`。
