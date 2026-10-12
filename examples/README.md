# 示例数据

典型数据样本，用于演示、联调与备份/还原演练。目录风格对齐 cndb：
`datasets/<场景名>/` 存放业务数据集，`backups/` 存放备份归档样本。

```
examples/
├── README.md                      本文件
├── backups/                       备份归档样本（iterd-backup-<版本>-v1-<UTC时间戳>.tar.gz）
└── datasets/
    ├── 项目-某型输送机机架结构设计/   典型工程设计项目数据集
    ├── 项目-边界异常数据/            边界与异常场景数据集
    ├── 项目-某型输送机传动轴与立柱设计/   检查器/求解器扩展功能数据集
    ├── 项目-编码与参数边界数据/       编码规范与数值参数边界数据集
    ├── 项目-某型输送机总装会签流程/   审批会签闭环数据集
    ├── 项目-多角色协作通知演练/       多角色通知与订阅演练数据集
    ├── 项目-BOM一致性边界数据/       BOM 一致性边界数据集
    └── 项目-焊接与连接件校核设计/     连接件求解器族与仿真超阈判定数据集
```

## 数据集：某型带式输送机机架结构设计

场景：带宽 800mm、机长 24m 带式输送机的机架结构设计，含 2 个项目（父子）、3 个迭代、
7 个产物、4 条规则、2 个规则集、2 个仿真模板，覆盖"上传产物 → 提交方案 → 审查流水线 → 运行结果"完整链路。

### 元数据定义（可直接映射到 API 入参）

| 文件 | 说明 |
| --- | --- |
| `项目结构.json` | 项目树、成员角色、迭代（含时间窗与状态机） |
| `规则库.json` | 规则条目：`checker_type` 与 `params` 对应 `GET /api/v1/checkers` 已注册检查器 |
| `规则集.json` | 规则集成员（经审查模板 rules/check 作业的 `with.rule_set` 引用生效） |
| `仿真模板.json` | 仿真求解器、默认参数与验收阈值（`{指标: {min\|max}}`） |
| `审查模板.yaml` | 审查流水线编排（提交方案触发运行） |
| `产物清单.csv` | 产物编码/名称/类别/所属迭代/上传文件名 |
| `产物元数据.csv` | 各产物版本的元数据（材料/尺寸/公差/粗糙度/设计者/校核者） |
| `载荷工况.csv` | 设计输入：四种工况载荷与安全系数要求 |
| `材料清单.csv` | BOM：零件编码、材料、规格、数量、重量 |
| `预期检查结果.json` | 预期结果：检查汇总与仿真结论的期望值 |

### 产物实体文件（上传用）

| 文件 | 类别 | 说明 |
| --- | --- | --- |
| `DRW-000_revA.dxf` | drawing | 迭代 1 概念方案总图（归档对象，不参与后续检查） |
| `DRW-001_revA.dxf` | drawing | 机架总装图，命名与元数据均合规 |
| `DRW-002_revA.dxf` | drawing | 横梁零件图，仿真验证对象 |
| `MOD-001_revA.step` | model | STEP AP203 三维模型 |
| `SPC-001_revA.md` | spec | 焊接、涂装与检验技术要求 |
| `CAL-001_revA.csv` | result | 横梁强度计算书（缺校核者会签） |
| `机架草图-最终版.dwg` | drawing | **典型问题数据**：文件名含中文且缺 `_revX` 后缀、元数据缺公差/粗糙度/校核者 |

### 预期结果

- 迭代 2 执行「机械设计通用规范」后 `CheckRun.summary` 应为
  `{"error": 2, "warning": 1, "info": 2, "artifacts": 6, "rules": 4}`；
  5 条发现项来源：文件名不规范（error）、缺公差（error + warning）、缺校核者（2 条 info）。
- 仿真：`BEAM-STATIC-CHECK`（8000N）结论 `pass`；`BEAM-HEAVY-CHECK`（15000N）三项指标全部超阈，结论 `fail`。
- 完整预期见 `预期检查结果.json`。

## 数据集：某型带式输送机托辊组件开发（边界异常数据）

场景：带宽 1000mm 带式输送机托辊组件开发，含 2 个项目（父子）、3 个迭代（active / planned / 子项目 active）、
6 个产物、5 条规则（含 1 条停用）、1 个规则集、3 个仿真模板，
专门覆盖文件名异常、元数据类型错误与字段缺失、planned 迭代、viewer 成员、
三种仿真判定结论（pass / 单指标超阈 / 全指标超阈）等边界场景。
14 个边界场景的完整清单见数据集内 `边界场景说明.csv`。

### 元数据定义（可直接映射到 API 入参）

| 文件 | 说明 |
| --- | --- |
| `项目结构.json` | 项目树、成员角色（含 admin 以 viewer 参与）、迭代（含 planned 状态） |
| `规则库.json` | 规则条目：含 `enabled=false` 停用规则（NAME-004）与 number/bool 类型校验规则 |
| `规则集.json` | 规则集成员（含停用规则，经审查模板引用生效） |
| `仿真模板.json` | 三个载荷档位模板共用辊筒轴几何与阈值 |
| `审查模板.yaml` | 审查流水线编排（rules 门禁 + 三档载荷并行仿真） |
| `产物清单.csv` | 产物编码/名称/类别/所属迭代/上传文件名 |
| `产物元数据.csv` | 各产物版本的元数据（数值/布尔字段刻意含类型错误样本） |
| `边界场景说明.csv` | 边界场景清单：编号、类别、数据特征、预期表现 |
| `零件清单.csv` | BOM：零件编码、材料、规格、数量、重量 |
| `预期检查结果.json` | 预期结果：检查汇总、发现项与三种仿真结论的期望值 |

### 产物实体文件（上传用）

| 文件 | 类别 | 说明 |
| --- | --- | --- |
| `RLL-101_revA.dxf` | drawing | 合规基准数据（元数据含数值 4.2 与布尔 true） |
| `RLL-102 revA.step` | drawing | **边界数据**：文件名含空格，触发 NAME-002 |
| `RLL-103_revA.step` | model | 合规 STEP 中性格式 |
| `托辊支架草图.dwg` | drawing | **边界数据**：中文文件名且无版本号，触发 NAME-002 |
| `SPC-101_revA.md` | spec | **边界数据**：元数据仅含设计者，触发缺失类 error + warning |
| `CAL-101_revA.csv` | result | **边界数据**：重量kg=约4.2、会签完成=已会签（类型错误）且缺设计者 |

### 预期结果

- 迭代 1 执行「托辊边界检查集」后 `CheckRun.summary` 应为
  `{"error": 4, "warning": 2, "info": 1, "artifacts": 6, "rules": 4}`；
  7 条发现项：文件名不规范 2 条（error）、数值类型错误 1 条（error）、布尔类型错误 1 条（warning）、
  元数据缺失 2 条（error + warning）、缺设计者 1 条（info）；停用规则 NAME-004 不产生发现项且不计入 rules。
- 仿真（引用 RLL-101）：`TRL-LIGHT-CHECK`（1200N）`pass`；
  `TRL-NOMINAL-CHECK`（2000N）仅挠度单指标超阈 `fail`；`TRL-OVERLOAD-CHECK`（4500N）三项全部超阈 `fail`。
- 完整预期见 `预期检查结果.json`。

## 数据集：某型输送机传动轴与立柱设计（检查器/求解器扩展）

场景：带宽 800mm 带式输送机传动系统设计，含 2 个项目（父子）、3 个迭代、
8 个产物、6 条规则、1 个规则集、4 个仿真模板，
覆盖新增的产物编码规范（artifact_code_convention）、重量数值范围（metadata_range）、
扩展名白名单（file_extension_whitelist）三类检查器与压杆稳定性（column_buckling）、
圆轴扭转（shaft_torsion）两个求解器的完整链路。

### 元数据定义（可直接映射到 API 入参）

| 文件 | 说明 |
| --- | --- |
| `项目结构.json` | 项目树、成员角色、迭代（含 closed 状态） |
| `规则库.json` | 规则条目：覆盖三类新检查器与两类元数据必填规则 |
| `规则集.json` | 规则集成员（经审查模板引用生效） |
| `仿真模板.json` | 轴扭转与立柱稳定两类求解器、四种判定工况模板 |
| `审查模板.yaml` | 审查流水线编排（串行门禁 / 并行仿真 / 门禁拦截三例） |
| `产物清单.csv` | 产物编码/名称/类别/所属迭代/上传文件名 |
| `产物元数据.csv` | 各产物版本的元数据（含重量超范围、缺校核者样本） |
| `零件清单.csv` | BOM：零件编码、材料、规格、数量、重量 |
| `预期检查结果.json` | 预期结果：检查汇总、发现项与四种仿真结论的期望值 |

### 审查流水线示例（审查模板.yaml）

数据集内 `审查模板.yaml` 提供三类典型流水线（`--with-review` 时按 `runs` 逐迭代提交并执行）：

| 模板编码 | 拓扑 | 演示语义 |
| --- | --- | --- |
| `AXLE-REVIEW` | 串行两级仿真（shaft-sim → needs → column-sim） | 全绿链路：作业依序执行，运行结论 `success` |
| `AXLE-REVIEW-PARALLEL` | 并行双仿真（shaft-sim 与 column-sim 同层无依赖） | 并行层展示：两作业同层并列，均通过后汇总 `success` |
| `AXLE-REVIEW-GATED` | 规则门禁 + 下游仿真（默认停用） | 门禁语义：当前迭代存在 error 级发现项，规则检查判 `failure`，下游两级仿真 `skipped` |

运行视图（前端「审查流水线」Tab）支持 GitHub Actions 风格展示：提交方案分组运行列表、
作业树按 needs 层级缩进并可展开平台内置步骤（setup / check / report 或 setup / solve / evaluate）、
步骤日志带相对时间戳与「仅看错误」过滤、运行中实时进度与日志流（WebSocket 推送）、
作业详情含发现项标注与仿真指标判定表。

### 产物实体文件（上传用）

| 文件 | 类别 | 说明 |
| --- | --- | --- |
| `DRW-300_revA.dxf` | drawing | 迭代 1 归档总图（归档对象，不参与迭代 2 检查） |
| `SHF-301_revA.step` | model | 合规基准；SHAFT 系列仿真引用对象 |
| `COL-301_revA.step` | model | 合规基准；COL 系列仿真引用对象 |
| `CAL-301_revA.csv` | result | 传动轴扭转计算书（合规） |
| `CAL-302_revA.csv` | result | **边界数据**：重量kg 误登记为 3200 超出上限，触发 RANGE-301 |
| `SPC-301_revA.md` | spec | **边界数据**：缺校核者会签，触发 PROC-301 |
| `exc-303_revA.dxf` | drawing | **边界数据**：小写编码且文件名小写开头，同时触发 CODE-301 与 NAME-301（演示规则独立性） |
| `EXC-302_revA.zip` | result | **边界数据**：压缩包格式不在白名单，触发 EXT-301 |

### 预期结果

- 迭代 2 执行「传动系统设计规范」后 `CheckRun.summary` 应为
  `{"error": 3, "warning": 1, "info": 1, "artifacts": 7, "rules": 6}`；
  5 条发现项：文件名不规范 1 条（error）、编码不规范 1 条（error）、重量超上限 1 条（error）、
  扩展名不在白名单 1 条（warning）、缺校核者 1 条（info）。
- 仿真：`SHAFT-NOMINAL-CHECK`（800N·m）`pass`；`SHAFT-OVERLOAD-CHECK`（1500N·m）三项全部超阈 `fail`；
  `COL-STABILITY-CHECK`（标准段）`pass`；`COL-SLENDER-CHECK`（细长杆）仅安全系数超阈 `fail`。
- 完整预期见 `预期检查结果.json`。

## 数据集：编码与参数边界数据

场景：产物编码规范与数值参数边界验证，含 2 个项目（父子）、3 个迭代（父#1 active / 父#2 planned）、
6 个产物、5 条规则（含 2 条停用，其中 1 条 checker_type 未注册）、1 个规则集、3 个仿真模板，
专门覆盖编码正反例、数值边界值（恰好等于上下限判定通过）、数值类型错误、大写扩展名、
停用规则跳过与计数、仿真非法参数（作业 failed）与压杆计算长度系数 μ=2.0 边界工况。
13 个边界场景的完整清单见数据集内 `边界场景说明.csv`。

### 元数据定义（可直接映射到 API 入参）

| 文件 | 说明 |
| --- | --- |
| `项目结构.json` | 项目树、成员角色、迭代（含 planned 状态不被推进） |
| `规则库.json` | 规则条目：含 `enabled=false` 停用规则与未注册 checker_type 停用规则（依赖前提见条目描述） |
| `规则集.json` | 规则集成员（含停用规则，经审查模板引用生效） |
| `仿真模板.json` | 正常对照（pass）/ 零扭矩非法参数（作业 failed）/ μ=2.0 压杆（单指标 fail）三类模板 |
| `审查模板.yaml` | 审查流水线编排（rules 门禁 + 三类边界工况仿真） |
| `产物清单.csv` | 产物编码/名称/类别/所属迭代/上传文件名 |
| `产物元数据.csv` | 各产物版本的元数据（含恰好等于上下限的边界值与非数值文本样本） |
| `边界场景说明.csv` | 边界场景清单：编号、类别、数据特征、预期表现 |
| `零件清单.csv` | BOM：零件编码、材料、规格、数量、重量 |
| `预期检查结果.json` | 预期结果：检查汇总、发现项与三类仿真结论（含 failed 作业）的期望值 |

### 产物实体文件（上传用）

| 文件 | 类别 | 说明 |
| --- | --- | --- |
| `RND-401_revA.step` | model | 合规基准数据（重量kg=500 恰好等于上限判定通过；元数据含数值与布尔字段）；SHAFT 系列仿真引用对象 |
| `rnd-402_revA.step` | model | **边界数据**：小写产物编码，触发 BND-CODE-401；COL 系列仿真引用对象 |
| `RND403_revA.dwg` | drawing | **边界数据**：缺连字符产物编码，触发 BND-CODE-401 |
| `CAL-401_revA.csv` | result | **边界数据**：重量kg 误填中文文本「约4.2」，触发 BND-RANGE-401 类型错误 |
| `RND-404_revA.STEP` | model | **边界数据**：大写扩展名（大小写不敏感判定通过）；重量kg=0.1 恰好等于下限判定通过 |
| `RND-405_revA.rar` | result | **边界数据**：压缩包格式不在白名单，触发 BND-EXT-401 |

### 预期结果

- 迭代 1 执行「编码与参数边界检查集」后 `CheckRun.summary` 应为
  `{"error": 3, "warning": 1, "info": 0, "artifacts": 6, "rules": 3}`；
  4 条发现项：编码不规范 2 条（error）、重量非数值 1 条（error）、扩展名不在白名单 1 条（warning）；
  停用规则 BND-NAME-404 / BND-CHK-405 不产生发现项且不计入 rules。
- 仿真：`BND-SHAFT-PASS-CHECK`（300N·m）`pass`；
  `BND-SHAFT-EDGE-CHECK`（零扭矩）求解器参数校验失败，作业 `status=failed` 且无指标输出；
  `BND-COL-EDGE-CHECK`（μ=2.0 一端固定一端自由，临界力折减 4 倍）仅安全系数超阈 `fail`。
- 完整预期见 `预期检查结果.json`。

## 数据集：某型输送机总装会签流程（审批会签闭环）

场景：带宽 800mm、机长 36m 带式输送机总装设计，1 个项目、1 个迭代、
4 个产物、4 条规则、1 个规则集、1 个仿真模板，
演示流水线内审批作业（approval/request）的会签闭环：
静态规则检查全绿 → sign-off 作业挂起等待人工会签（运行置 waiting）→
会签达成（min_count=1）后自动续跑下游纵梁静强度仿真。

### 元数据定义（可直接映射到 API 入参）

| 文件 | 说明 |
| --- | --- |
| `项目结构.json` | 项目、成员角色（designer / reviewer）、1 个 active 迭代 |
| `规则库.json` | 规则条目：命名、材料、公差与工艺会签登记四类检查 |
| `规则集.json` | 全局规则集「总装会签检查集」（经审查模板引用生效） |
| `仿真模板.json` | 纵梁静强度校核模板（会签通过后执行，结论 pass） |
| `审查模板.yaml` | 会签流水线编排（rules 门禁 → approval/request → 仿真） |
| `产物清单.csv` | 产物编码/名称/类别/所属迭代/上传文件名 |
| `产物元数据.csv` | 各产物版本的元数据（全部齐全，保证检查全绿推进到会签） |
| `预期检查结果.json` | 预期结果：检查汇总、发现项、会签参数与仿真结论的期望值 |

### 产物实体文件（上传用）

| 文件 | 类别 | 说明 |
| --- | --- | --- |
| `ASM-001_revA.dxf` | drawing | 合规总装图（元数据齐全） |
| `DRW-101_revA.dxf` | drawing | 合规纵梁零件图，会签后仿真绑定对象 |
| `MOD-101_revA.step` | model | 合规 STEP 三维模型 |
| `SPC-101_revA.md` | spec | 总装技术要求（含会签流程说明） |

### 预期结果

- seed 预执行后运行停在 `waiting`：rules/check 作业 CheckRun.summary 应为
  `{"error": 0, "warning": 0, "info": 0, "artifacts": 4, "rules": 4}`（全绿无发现项）；
- sign-off 作业进入待办中心，approvers 为 reviewer（用户名命中，演示账号为项目 reviewer 角色）
  与 admin（超管恒在范围），min_count=1；
- 任一审批人签署通过后运行自动续跑，下游纵梁仿真 `BEAM-ASM-CHECK` 结论 `pass`
  （max_stress=108MPa、deflection≈31.46mm（阈值 35mm）、n≈2.18）。
- 完整预期见 `预期检查结果.json`。

## 数据集：焊接与连接件校核设计（连接件求解器族与仿真超阈判定）

场景：焊接支架、螺栓法兰与齿轮轴连接件校核，1 个项目、1 个迭代、4 个产物、4 条规则、
1 个规则集、4 个仿真模板，演示三个连接件求解器（`weld_fillet_shear` / `bolt_shear` /
`gear_tooth_bending`）与仿真 verdict 的 pass / fail 双路径：静态规则检查全绿后并行执行四项仿真，
两项通过、两项超阈失败（螺栓过载 / 焊脚过薄）。判定 fail 仅落红 X 于该作业 conclusion，
不阻断兄弟作业与运行推进。

### 元数据定义（可直接映射到 API 入参）

| 文件 | 说明 |
| --- | --- |
| `项目结构.json` | 项目、成员角色（designer / reviewer）、1 个 active 迭代 |
| `规则库.json` | 规则条目：命名、材料、公差与工艺会签登记四类检查 |
| `规则集.json` | 全局规则集「连接件校核检查集」（经审查模板引用生效） |
| `仿真模板.json` | 四项连接件校核模板（WLD-PASS / BLT-OVERLOAD / GEAR-PASS / WLD-THIN） |
| `审查模板.yaml` | 连接件校核流水线编排（rules 门禁 → 四项仿真并行） |
| `产物清单.csv` | 产物编码/名称/类别/所属迭代/上传文件名 |
| `产物元数据.csv` | 各产物版本的元数据（全部齐全，保证检查全绿推进到仿真） |
| `预期检查结果.json` | 预期结果：检查汇总、发现项与四项仿真 verdict / 超阈键 / 指标基线 |

### 产物实体文件（上传用）

| 文件 | 类别 | 说明 |
| --- | --- | --- |
| `WLD-501_revA.dxf` | drawing | 焊接支架图，两项角焊缝校核绑定产物 |
| `BLT-501_revA.dxf` | drawing | 螺栓连接法兰图，螺栓组剪切校核绑定产物 |
| `GR-501_revA.dxf` | drawing | 齿轮轴零件图，齿根弯曲校核绑定产物 |
| `DRW-501_revA.dxf` | drawing | 连接件布置图（合规） |

### 预期结果

- seed 预执行后 rules/check 作业 CheckRun.summary 应为
  `{"error": 0, "warning": 0, "info": 0, "artifacts": 4, "rules": 4}`（全绿无发现项）；
- 四项仿真并行执行：`WLD-PASS`（τ≈11.905MPa、n≈6.72）与 `GEAR-PASS`（σ≈191.57MPa、n≈1.04）
  结论 `pass`；`BLT-OVERLOAD`（τ≈318.31MPa、n≈0.25）与 `WLD-THIN`（τ≈95.238MPa、n≈0.84）
  结论 `fail` 且 `shear_stress`、`safety_factor` 双双超阈。
- 完整预期见 `预期检查结果.json`。

## 使用方式

### 1. 载入示例数据

```bash
# 载入到 .iterd-example 数据目录并预执行审查流水线（默认库 .iterd-example/iterd.db）
uv run python scripts/load_example.py --with-review

# 仅载入结构化数据（不触发流水线）
uv run python scripts/load_example.py

# 指定数据目录与数据库
uv run python scripts/load_example.py --data-dir .iterd-example --with-review

# 载入指定数据集
uv run python scripts/load_example.py --dataset examples/datasets/项目-某型输送机机架结构设计

# 载入传动轴与立柱设计数据集并预执行审查流水线
# （串行全绿 AXLE-REVIEW + 并行双仿真 AXLE-REVIEW-PARALLEL，GATED 默认停用不触发）
uv run python scripts/load_example.py --dataset examples/datasets/项目-某型输送机传动轴与立柱设计 --with-review

# 载入编码与参数边界数据集（含停用规则与非法参数仿真边界）
uv run python scripts/load_example.py --dataset examples/datasets/项目-编码与参数边界数据 --with-review
```

脚本幂等：项目/规则/规则集/仿真模板/审查模板按编码或名称跳过已存在记录。
`--with-review` 按各数据集 `审查模板.yaml` 的 `runs` 节逐迭代提交方案、
启动进程内 worker 执行流水线并等待终态，逐作业打印检查汇总与仿真结论，供与
`预期检查结果.json` 比对。

载入后启动服务查看：`uv run iterd serve`，默认管理员 `admin / admin1234`，
演示用户 `designer / designer123`、`reviewer / reviewer123`。

### 2. 备份与还原演练

```bash
# 用示例库生成备份归档
ITERD_DATA_DIR=$PWD/.iterd-example uv run iterd backup --output examples/backups/

# 查看归档元信息（版本、表清单与行数、对象统计）
uv run python -c "from pathlib import Path; from iterd.core.backup import inspect_backup; print(inspect_backup(Path('examples/backups').glob('*.tar.gz').__next__()))"

# 还原到示例库
ITERD_DATA_DIR=$PWD/.iterd-example uv run iterd restore examples/backups/iterd-backup-0.1.0-v1-*.tar.gz
```

`examples/backups/` 下的归档为真实备份产物（`iterd-backup-0.1.0-v1-<时间戳>.tar.gz`），
内含 `manifest.json`、`data/iterd.db` 与 `objects/`（内容寻址，7 个产物对象），可直接用于还原验证。
