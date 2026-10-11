# 检查器与求解器扩展 Implementation Plan

> Status: APPROVED
> Source: user request（"针对功能拓展制定开发计划，并补充更多典型案例"）
> Mode: (default) 完整 Planner → Architect → Critic 循环
> Iterations: 2 / 3
> Author: user
> Last updated: 2026-10-11

## Requirements summary

本 plan 服务两个目标：(1) 功能拓展——按注册表架构预留的拓展点新增规则检查器与仿真求解器，从 2 检查器 / 1 求解器扩展到 5 检查器 / 3 求解器，前端零改动；(2) 补充典型案例——新增 2 个数据集完整覆盖新功能，延续"上传产物 → 规则检查 → 仿真验证 → 基线归档"链路风格，含预期检查结果自检基线。

方向说明：用户提问在非交互环境超时未应答，按全局规则采用推荐默认（检查器+求解器扩展 / 新功能配套场景），**待用户复核**。

## Acceptance criteria

- AC-1 `GET /api/v1/rules/checkers` 返回 ≥5 个检查器，含 `artifact_code_convention`、`metadata_range`、`file_extension_whitelist`（[routers.py:22-27](file:///workspace/src/iterd/plugins/rules/routers.py) 动态下发，无硬编码）。
- AC-2 `GET /api/v1/solvers` 返回 ≥3 个求解器，含 `column_buckling`、`shaft_torsion`，各带完整 `inputs` / `metrics` 规格（[routers.py:19-24](file:///workspace/src/iterd/plugins/simulation/routers.py)）。
- AC-3 三个新检查器对正反例数据产生预期 findings：单元测试断言 severity / location / message 关键词。
- AC-4 两个新求解器输出与手算公式值一致（`math.isclose` 相对误差 1e-9）；非法参数（≤0）抛 `IterdError` 且 code 为 `ITERD-SOLVER_ERROR`。
- AC-5 新数据集可被 `scripts/load_example.py --dataset <路径> --with-check --with-sim` 完整载入并执行，`CheckRun.summary` 与 `预期检查结果.json` 的 `expected_summary` 完全一致，仿真 verdict 与 `expected_simulations` 一致。
- AC-6 全部既有测试语义不变：`iterd.checkers` / `iterd.solvers` 对外导入符号（见 Implementation steps 步骤 4/9 清单）经 re-export 保持兼容。
- AC-7 `make check` 全绿（lint + typecheck + coverage ≥95%）。

## RALPLAN-DR

### Principles

1. 零平台改动：新检查器/求解器仅经注册表（[checkers/__init__.py:61-86](file:///workspace/src/iterd/checkers/__init__.py#L61-L86)、[solvers/__init__.py:50-89](file:///workspace/src/iterd/solvers/__init__.py#L50-L89)）扩展，不改 rules / simulation 插件编排代码。
2. 结构合规：遵循全局规则 code-structure——`__init__.py` 只做门面，业务实现放子模块；本次重构 checkers / solvers 包时治理存量违规。
3. 确定性可断言：新求解器沿用解析公式（非数值迭代），单元测试可精确断言到浮点精度。
4. 数据集自包含：完全复用现有数据集文件格式与 [load_example.py](file:///workspace/scripts/load_example.py) 载入路径，不新增载入代码。
5. 前端零改动：manifest 动态下发（`checker_manifest` / `solver_manifest`），动态表单自动适配新求解器。

### Decision drivers

1. 演示/联调价值：功能面 2+1 → 5+3，直接扩展平台演示能力。
2. 边际维护成本：注册表是架构显式预留的拓展路径（模块 docstring 即声明"新增检查器/求解器不改平台代码"）。
3. 可验证性：确定性公式 + 预期基线，全部 AC 二值可验证。

### Viable options

**Option A: 就地扩展（最小 diff）**
- 实现思路：新检查器类直接追加进 `checkers/__init__.py`、新求解器追加进 `solvers/__init__.py`，模块底部追加注册调用。
- 改动文件：2 个源文件 + 测试 + 数据集。
- Pros: diff 最小；注册时机不变。
- Cons: `checkers/__init__.py` 从 151 行涨到约 300 行、`solvers/__init__.py` 涨到约 400 行；与全局规则 code-structure（`__init__.py` 禁止定义类/函数，仅做门面）的存量违规进一步加剧。

**Option B: 子模块化拆分 + 扩展（结构合规）[chosen]**
- 实现思路：`checkers/` 拆为 `registry.py`（协议+注册表）、`convention.py`、`metadata.py`；`solvers/` 拆为 `registry.py`、`beam.py`、`column.py`、`shaft.py`；`__init__.py` 仅 re-export 并触发注册。
- 改动文件：2 个包重组 + 3 新检查器 + 2 新求解器 + 测试 + 数据集。
- Pros: 符合 code-structure 的"重构时逐步治理"条款；每类一模块，后续扩展只加文件；导入路径经 re-export 完全兼容。
- Cons: diff 变大（纯移动 + 新增）；需保证 re-export 完整与注册时机正确。

**Option C: 仅扩展检查器 + 多数据集**
- 实现思路：只加 3 个检查器与 3-4 个数据集，不动求解器。
- Pros: 改动更小。Cons: 仿真面仍单薄（1 个求解器），"功能拓展"感知弱；invaliation rationale：与用户请求的"功能拓展"完整性不匹配，求解器侧拓展点是架构同样显式预留的方向，无理由单侧放弃。

## Planner draft（v2，基于 Option B 的实施设计）

### 新检查器规格（均零协议改动，仅消费现有 `ArtifactRef` 字段）

| checker_type | params 结构 | 检查逻辑 | finding 设计 |
|---|---|---|---|
| `artifact_code_convention` | `{"pattern": str}` | `re.match(pattern, artifact.artifact_code)` | location=`artifact_code`，message=`产物编码 {code} 不符合规范 {pattern}`；空 pattern 跳过（对齐 [FilenameConventionChecker](file:///workspace/src/iterd/checkers/__init__.py#L99-L103) 风格） |
| `metadata_range` | `{"ranges": {键: {"min"?: num, "max"?: num}}}` | 逐键：缺失跳过（职责归 metadata_required）；类型非数值（bool 显式排除，Python 中 bool 是 int 子类）记"应为数值"；越界记"超出范围 [min, max]" | 每规则聚合一条（`; ` 连接），location=`metadata`，对齐 [MetadataRequiredChecker](file:///workspace/src/iterd/checkers/__init__.py#L127-L147) 风格 |
| `file_extension_whitelist` | `{"extensions": [".dxf", ...]}` | `Path(filename).suffix.lower()` 不在清单 → 发现 | location=`filename`；空/缺失 extensions 清单 → 无发现（保守放行，对齐既有"缺配置即跳过"风格） |

### 新求解器规格（确定性解析公式，对齐 `beam_static` 风格）

**`column_buckling`（压杆稳定性，Euler）**
- 输入：`axial_load`(N, 默认 10000) / `length`(mm, 1500) / `width`(mm, 60) / `height`(mm, 60) / `modulus`(MPa, 206000) / `effective_length_factor`(-, 1.0)
- 公式：`I = min(w·h³/12, h·w³/12)`（弱轴）；`critical_load = π²·E·I / (μ·L)²`；`actual_stress = P/(w·h)`；`safety_factor = critical_load / axial_load`
- 输出指标：`critical_load`(N) / `actual_stress`(MPa) / `safety_factor`(-)
- 校验：全部参数必须为正（对齐 [beam_static 的 run() 校验](file:///workspace/src/iterd/solvers/__init__.py#L121-L126)）

**`shaft_torsion`（圆轴扭转）**
- 输入：`torque`(N·m, 500) / `diameter`(mm, 40) / `length`(mm, 500) / `shear_modulus`(MPa, 79000) / `allowable_shear`(MPa, 60)
- 公式：`T = torque×1000`(N·mm)；`J = π·d⁴/32`；`max_shear_stress = 16T/(π·d³)`；`twist_angle = T·L/(G·J)·180/π`(°)；`safety_factor = allowable_shear / max_shear_stress`
- 输出指标：`max_shear_stress`(MPa) / `twist_angle`(°) / `safety_factor`(-)

### 数据集 3：项目-某型输送机传动轴与立柱设计（新功能完整链路）

项目树：父 `AXLE-2026` + 子 `AXLE-CALC-2026`，3 个迭代（父#1 closed / 父#2 active / 子#1 active），父#1 一条基线。检查与仿真都发生在父#2。

产物 8 个（7 个在父#2 参与检查 + 1 个在父#1 做基线快照）：

| 产物编码 | 文件名 | 类别 | 设计用途 |
|---|---|---|---|
| DRW-300 | DRW-300_revA.dxf | drawing | 父#1 基线总图，不参与检查 |
| SHF-301 | SHF-301_revA.step | model | 合规；轴仿真绑定对象 |
| COL-301 | COL-301_revA.step | model | 合规；立柱仿真绑定对象 |
| CAL-301 | CAL-301_revA.csv | result | 合规 |
| CAL-302 | CAL-302_revA.csv | result | 元数据 `重量kg=3200` 超范围 → RANGE-301 error |
| SPC-301 | SPC-301_revA.md | spec | 元数据缺校核者 → PROC-301 info |
| exc-303 | exc-303_revA.dxf | drawing | 小写编码 → CODE-301 error；文件名小写 → NAME-301 error（双发现，演示规则独立性） |
| EXC-302 | EXC-302_revA.zip | result | 扩展名不在白名单 → EXT-301 warning（编码合规、文件名合规，单点触发） |

规则 6 条（category 须符合 [schemas.py:16](file:///workspace/src/iterd/plugins/rules/schemas.py#L16) 枚举 `drafting|tolerance|material|process`）：

| code | checker_type | 要点 | severity |
|---|---|---|---|
| NAME-301 | filename_convention | pattern 同 DRAFT-001 | error |
| CODE-301 | artifact_code_convention | `^[A-Z]{3}-\d{3,}$` | error |
| RANGE-301 | metadata_range | `重量kg: {min: 0.1, max: 500}` | error |
| EXT-301 | file_extension_whitelist | `[.dxf,.dwg,.step,.stp,.csv,.md]` | warning |
| MATL-301 | metadata_required | 材料/尺寸 str | error |
| PROC-301 | metadata_required | 设计者/校核者 str | info |

规则集"传动系统设计规范"（6 条全量）绑定父#2。命中矩阵推演（7 产物 × 6 规则）：NAME×1（exc-303）、CODE×1（exc-303）、RANGE×1（CAL-302）、EXT×1（EXC-302）、MATL×0、PROC×1（SPC-301）。

**expected_summary = `{"error": 3, "warning": 1, "info": 1, "artifacts": 7, "rules": 6}`**，5 条 findings。

仿真模板 4 个（verdict 覆盖 pass / 单指标 fail / 全指标 fail；数值实现时按公式精确重算后回填模板 description）：

| code | solver | 参数要点 | 阈值方向 | 预期 |
|---|---|---|---|---|
| SHAFT-NOMINAL-CHECK | shaft_torsion | torque 800 N·m, d 45mm | 三项全过 | pass |
| SHAFT-OVERLOAD-CHECK | shaft_torsion | torque 1500 N·m | 应力/扭角/安全系数全超 | fail（全指标） |
| COL-STABILITY-CHECK | column_buckling | P 50kN, 60×60×1500, μ=1 | 富余量大 | pass |
| COL-SLENDER-CHECK | column_buckling | P 30kN, 40×40×4000 细长杆 | 仅安全系数不足 | fail（单指标） |

文件清单：`项目结构.json`、`规则库.json`、`规则集.json`、`仿真模板.json`、`产物清单.csv`、`产物元数据.csv`、`零件清单.csv`、`预期检查结果.json` + 8 个实体文件。`.zip` 上传走 [load_example.py:28-36](file:///workspace/scripts/load_example.py#L28-L36) 的 octet-stream 回落，无需改代码。

### 数据集 4：项目-编码与参数边界数据（新检查器/求解器边界）

项目树：父 `BND-2026` + 子 `BND-EDGE-2026`，3 个迭代（父#1 active / 父#2 planned / 子#1 active）。检查与仿真在父#1。

产物 6 个（均在父#1）：`RND-401_revA.step`（合规基准，重量kg=500 恰好等于 max 边界 → 通过；元数据含数值 4.2 与布尔 true）、`rnd-402_revA.step`（小写编码 → CODE error）、`RND403_revA.dwg`（缺连字符编码 → CODE error）、`CAL-401_revA.csv`（`重量kg="约4.2"` 字符串 → RANGE 类型错误 error）、`RND-404_revA.STEP`（大写扩展名 → 大小写不敏感通过，重量kg=0.1 恰好等于 min 边界 → 通过）、`RND-405_revA.rar`（→ EXT warning）。

规则 5 条（含 2 条停用）：`BND-CODE-401`（error）、`BND-RANGE-401`（error）、`BND-EXT-401`（warning）、`BND-NAME-404`（filename_convention，`enabled=false`）、`BND-CHK-405`（`checker_type: "no_such_checker"`，`enabled=false`——依赖 [create_rule 不校验 checker_type](file:///workspace/src/iterd/plugins/rules/services.py#L42-L48) 与 [执行时 enabled 过滤](file:///workspace/src/iterd/plugins/rules/services.py#L318-L326) 两处实现，载入与检查均安全）。

**expected_summary = `{"error": 3, "warning": 1, "info": 0, "artifacts": 6, "rules": 3}`**（停用规则不计 rules、不产生发现），4 条 findings。

仿真模板 3 个：`BND-SHAFT-PASS-CHECK`（torque 300 N·m → pass，正常对照组）、`BND-SHAFT-EDGE-CHECK`（torque 0 → 参数非正 → 作业 `status=failed`，预期检查结果的该条目增加 `"status": "failed"` 字段表达）、`BND-COL-EDGE-CHECK`（μ=2.0 一端固定一端自由，Fcr 折减 4 倍 → 单指标 fail）。

另含 `边界场景说明.csv`（约 12 条：小写/缺连字符编码、类型错误、恰好等于 min/max 边界值通过、大写扩展名、停用规则、未注册 checker_type 停用规则、planned 迭代不参与、仿真参数非法作业 failed、压杆 μ 边界工况）与 `零件清单.csv`。

## Architect challenge

### Steelman against Option A（v1，Planner 当时倾向 A）

反方核心论点：全局规则 code-structure 为 alwaysApply，明确"`__init__.py` 禁止定义函数、类、dataclass"，并规定"存量违规在重构时逐步治理"。本次向 checkers / solvers 包新增 5 个类，正是该规则定义的"重构时"；选 A 意味着主动把 `__init__.py` 推到 300-400 行，违规存量翻倍，且未来每个新检查器都在加剧。A 省下的拆分成本会在第三次扩展时加倍偿还。

若反驳成立（成立），plan 应改为 Option B：注册表与协议独立 `registry.py`（避免实现模块 import 包根造成循环导入——这是拆分的关键正确性约束），实现模块从 `.registry` 导入并在模块底部自注册，`__init__.py` import 实现模块即触发注册，对外 re-export 保持兼容。

### Tradeoff tensions

- 最小代码 vs 结构合规：baseline 说"只动必须动的"，code-structure 说"重构时治理存量"。取舍依据：code-structure 是用户全局 alwaysApply 规则，优先级高于通用最小化偏好；且拆分是机械移动（无逻辑变更），测试套件即兼容性验收，风险可控。
- diff 规模 vs 演示进度：B 的 diff 约为 A 的 1.5 倍。取舍依据：本 plan 不涉线上交付窗口，结构收益是长期复利。

### Synthesis path

A 的"注册时机不变"与 B 的"结构合规"可融合：注册调用随实现类留在各子模块底部（语义与现状完全一致，只是物理位置从 `__init__.py` 底部移到子模块底部），`__init__.py` 通过 import 子模块隐式完成注册引导——对外行为零变化。

## Critic verdict

| 维度 | 状态 | 备注 |
|---|---|---|
| Principle-option consistency | ✓ | Option B 与"结构合规"原则一致；零平台改动（rules/simulation 编排代码不动） |
| Fair alternative exploration | ✓ | A/B/C 均为真候选；C 附 invalidation rationale |
| Risk mitigation clarity | ✓ | 每条 risk 均有可执行 mitigation（见下表） |
| AC testability | ✓ | AC-1/2 API 断言，AC-3/4 单元断言，AC-5 载入命令 + 基线比对，AC-6/7 测试套件与门禁 |
| Verification concreteness | ✓ | 全部给出命令与判定值 |
| File/line coverage | ✓ | 实施步骤 15 条中 14 条 cite 具体文件/行号 |
| Pre-mortem present | N/A | 非 deliberate 模式 |

### Verdict: APPROVED（v2；v1 为 REVISE，见 Review trail）

### Reservations

1. 数据集 4 的"未注册 checker_type 停用规则"边界依赖两处实现细节（`create_rule` 不校验 + 执行时 enabled 过滤）。若后续在 `create_rule` 增加注册校验，该样本载入将 422。可接受的演示脆弱性，须在 `边界场景说明.csv` 中标注依赖前提。
2. `预期检查结果.json` 无自动化断言（tests 不引用 examples/，已核实），AC-5 验证依赖人工比对 stdout 与基线文件。建议 follow-up 补 slow 标记的冒烟测试。

## Implementation steps

阶段划分（对齐迭代工作流）：P1=步骤 1-4+10，P2=步骤 5-9+11，P3=步骤 12，P4=步骤 13-14，P5=步骤 15。

1. 新建 `src/iterd/checkers/registry.py`：迁移 [checkers/__init__.py:15-86](file:///workspace/src/iterd/checkers/__init__.py#L15-L86)（ArtifactRef / RuleRef / Finding / CheckerAdapter / 注册表四函数），中文 docstring，无包内依赖（防循环导入的根）。
2. 新建 `src/iterd/checkers/convention.py`：迁移 [L89-112](file:///workspace/src/iterd/checkers/__init__.py#L89-L112) FilenameConventionChecker；新增 ArtifactCodeConventionChecker、FileExtensionWhitelistChecker（规格见 Planner draft）；模块底部 `register_checker` ×3。
3. 新建 `src/iterd/checkers/metadata.py`：迁移 [L115-147](file:///workspace/src/iterd/checkers/__init__.py#L115-L147) MetadataRequiredChecker；新增 MetadataRangeChecker（bool 显式排除）；底部注册 ×2。
4. 重写 `src/iterd/checkers/__init__.py` 为 facade：`from .registry import ...` + `from .convention import ...` + `from .metadata import ...` + `__all__`；re-export 符号 ≥ [tests/test_checkers_cli.py:10-17](file:///workspace/tests/test_checkers_cli.py#L10-L17)（ArtifactRef, FilenameConventionChecker, MetadataRequiredChecker, RuleRef, get_checker, registered_checkers）∪ [rules/services.py:12](file:///workspace/src/iterd/plugins/rules/services.py#L12)（ArtifactRef, Finding, get_checker）∪ 新增类。
5. 新建 `src/iterd/solvers/registry.py`：迁移 [solvers/__init__.py:14-89](file:///workspace/src/iterd/solvers/__init__.py#L14-L89)（SimInput / Metric / SolverAdapter / 注册表 / manifest / default_inputs）+ [L145-152](file:///workspace/src/iterd/solvers/__init__.py#L145-L152) `_number`（三求解器共用）。
6. 新建 `src/iterd/solvers/beam.py`：迁移 [L92-142](file:///workspace/src/iterd/solvers/__init__.py#L92-L142) BeamStaticSolver，底部注册。
7. 新建 `src/iterd/solvers/column.py`：ColumnBucklingSolver（Euler 压杆，规格见 Planner draft），底部注册。
8. 新建 `src/iterd/solvers/shaft.py`：ShaftTorsionSolver（圆轴扭转），底部注册。
9. 重写 `src/iterd/solvers/__init__.py` 为 facade：re-export 对齐现有 [`__all__` L158-166](file:///workspace/src/iterd/solvers/__init__.py#L158-L166) ∪ [simulation/services.py:14](file:///workspace/src/iterd/plugins/simulation/services.py#L14)（Metric, SimInput, SolverAdapter, default_inputs, get_solver）∪ 新增类。
10. 扩充 `tests/test_checkers_cli.py`：复用既有 `_artifact` / `_rule` 辅助（[L21-34](file:///workspace/tests/test_checkers_cli.py#L21-L34)），为 3 个新检查器补正反例与边界（空 pattern 放行、恰好边界值通过、bool 排除、大写扩展名不敏感、空清单放行）。
11. 新建 `tests/test_solvers.py`：两新求解器公式精确断言（`math.isclose(rel_tol=1e-9)`，手算基准值独立推导）+ 参数 ≤0 抛 `IterdError` 断言。
12. 新建 `examples/datasets/项目-某型输送机传动轴与立柱设计/`：按 Planner draft 规格产出 8 个元数据/清单文件 + 8 个实体文件；`预期检查结果.json` 的 summary 按 `{"error":3,"warning":1,"info":1,"artifacts":7,"rules":6}` 落盘。
13. 新建 `examples/datasets/项目-编码与参数边界数据/`：10 类文件 + 6 实体文件；`边界场景说明.csv` 标注未注册 checker_type 样本的依赖前提（Critic reservation 1）。
14. 更新 `examples/README.md`：目录树（[L7-13](file:///workspace/examples/README.md#L7-L13)）补两个数据集；对齐 [L15-95](file:///workspace/examples/README.md#L15-L95) 章节风格各增一节；使用方式（[L97-119](file:///workspace/examples/README.md#L97-L119)）补两条载入命令。
15. 验证收尾：两条 `load_example --with-check --with-sim` 载入并核对基线 → `make check` 全绿。

## Workspace setup

- 已核实：`git status --short` 干净，当前分支 `trae/agent-jIhEMX`（非 main/master/release），最近提交 f12ba6b。
- 分支非主干且工作区干净：默认直接在当前分支实施，不开 worktree；如需隔离，推荐 `git worktree add -b codex/checker-solver-expansion ../iterd-checker-solver-expansion`。此默认**待用户复核**。
- `.claude/artifacts/` 与 `.trae/` 均为本地协作产物，不入版本库（遵循 commit 规则的提交范围排除）。

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| 包拆分破坏外部导入路径（rules/services.py L12、simulation/services.py L14、tests/test_checkers_cli.py L10-17） | 步骤 4/9 的 re-export 符号清单以这三处实际导入面为准；既有测试套件零改动通过即兼容性验收（AC-6） |
| 循环导入（实现模块 ↔ 注册表） | 注册表独立 `registry.py` 且不依赖包内兄弟模块；实现模块用 `from .registry import ...`；`__init__.py` 最后 import 实现模块 |
| 求解器公式/单位换算错误（N·m→N·mm、MPa=N/mm²、弧度→度） | 单元测试用独立手算值 `math.isclose(rel_tol=1e-9)` 断言；模板 description 记录中间值便于复核 |
| 数据集预期 summary 与实际不符 | 命中矩阵已预先推演（见 Planner draft）；实现时先跑 `--with-check` 打印实际 summary 回填基线文件再定稿 |
| coverage <95% | 新检查器/求解器均为纯函数，正反例+边界全覆盖；空 params/非法参数配测试 |
| `.zip` / `.rar` 上传 content_type 未定义 | [load_example.py:28-36](file:///workspace/scripts/load_example.py#L28-L36) 已有 octet-stream 回落，验证步骤确认 |
| 未注册 checker_type 边界样本随版本演进失效 | 边界场景说明.csv 标注依赖前提（Critic reservation 1）；该样本停用，不阻塞检查链路 |

## Verification steps

- AC-1：`uv run pytest tests/test_checkers_cli.py::test_registry -v` → `registered_checkers()` 含 5 类型（既有断言为 `>=`，不会误绿，另在新增测试中断言全量集合）。
- AC-2：`uv run pytest tests/test_simulation_api.py::test_solvers_manifest -v` → 含 3 求解器且新求解器带 inputs/metrics。
- AC-3/4：`uv run pytest tests/test_checkers_cli.py tests/test_solvers.py -v` 全绿。
- AC-5：`uv run python scripts/load_example.py --dataset examples/datasets/项目-某型输送机传动轴与立柱设计 --with-check --with-sim`，比对 stdout 的 summary/verdict 与 `预期检查结果.json`；同法验证数据集 4（含作业 failed 的表达）。
- AC-6：`uv run pytest -m "not slow"` 既有测试全绿、零语义改动。
- AC-7：`make check`（lint + typecheck + cov）全绿。

## ADR

- **Decision**：将 checkers / solvers 包子模块化（registry + 按域实现模块 + facade `__init__`），并新增 3 检查器（artifact_code_convention / metadata_range / file_extension_whitelist）与 2 求解器（column_buckling / shaft_torsion），配套 2 个典型案例数据集。
- **Drivers**：演示价值 / 边际维护成本 / 可验证性；**结构合规（用户全局规则 code-structure）在 A/B 之间起了决定性作用**。
- **Alternatives considered**：Option A 就地扩展（rejected：alwaysApply 规则违规加剧，`__init__.py` 膨胀至 300-400 行）；Option B 子模块化+扩展（chosen）；Option C 仅检查器（rejected：仿真拓展点同样显式预留，单侧放弃无依据）。
- **Why chosen**：注册表是架构显式预留的拓展路径；code-structure 的"重构时逐步治理"条款恰好覆盖本次时机；拆分为机械移动、既有测试即兼容性验收，风险可控。
- **Consequences**：diff 规模增大约 1.5 倍（纯移动+新增）；对外导入路径不变；rules/simulation 编排代码与前端零改动；后续新增检查器/求解器只需增加子模块文件。
- **Follow-ups**：数据集载入 slow 冒烟测试（自动化 AC-5）；跨产物检查协议升级（BOM 一致性等，需 `check()` 协议扩展，超出本期）；更多行业场景数据集（钣金/焊接/电气）。

## Review trail

- Planner draft v1: 倾向 Option A（就地扩展，最小 diff），3 检查器 + 2 求解器 + 2 数据集。
- Architect challenge v1: steelman 指出 code-structure alwaysApply 违规 + 循环导入正确性约束（registry 必须独立）；tension"最小代码 vs 结构合规"；提出 synthesis（注册随实现类留子模块底部，`__init__` import 触发）。
- Critic verdict v1: REVISE — Principle-option consistency ✗（Option A 与结构合规原则冲突）；待改项：改用子模块化方案、补 re-export 符号清单、明确注册时机与循环导入规避设计。
- Planner draft v2: 采纳 Option B，补齐 registry 独立性约束、re-export 导入面清单（三处实际引用）、数据集命中矩阵与 expected_summary 推演。
- Architect challenge v2: 确认无循环导入路径（registry 无包内依赖）；剩余 tension（diff 规模 vs 结构收益）已记录取舍依据。
- Critic verdict v2: APPROVED with 2 reservations（边界样本实现依赖、预期基线无自动化断言）。
- Final iterations: 2 / 3

## Open questions

- 数据集验证自动化：本期人工比对，是否补 slow 冒烟测试由后续迭代决定。
- worktree 选择：默认在当前分支 `trae/agent-jIhEMX` 实施，待用户复核。
- 方向默认复核：本 plan 的拓展方向与案例主题为非交互环境下的推荐默认，待用户复核。
