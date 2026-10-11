# 示例数据

典型数据样本，用于演示、联调与备份/还原演练。目录风格对齐 cndb：
`datasets/<场景名>/` 存放业务数据集，`backups/` 存放备份归档样本。

```
examples/
├── README.md                      本文件
├── backups/                       备份归档样本（iterd-backup-<版本>-v1-<UTC时间戳>.tar.gz）
└── datasets/
    └── 项目-某型输送机机架结构设计/   典型工程设计项目数据集
```

## 数据集：某型带式输送机机架结构设计

场景：带宽 800mm、机长 24m 带式输送机的机架结构设计，含 2 个项目（父子）、3 个迭代、
7 个产物、4 条规则、2 个规则集、2 个仿真模板，覆盖"上传产物 → 规则检查 → 仿真验证 → 基线归档"完整链路。

### 元数据定义（可直接映射到 API 入参）

| 文件 | 说明 |
| --- | --- |
| `项目结构.json` | 项目树、成员角色、迭代（含时间窗与状态机）、基线 |
| `规则库.json` | 规则条目：`checker_type` 与 `params` 对应 `GET /api/v1/checkers` 已注册检查器 |
| `规则集.json` | 规则集成员与迭代绑定关系 |
| `仿真模板.json` | 仿真求解器、默认参数与验收阈值（`{指标: {min\|max}}`） |
| `产物清单.csv` | 产物编码/名称/类别/所属迭代/上传文件名 |
| `产物元数据.csv` | 各产物版本的元数据（材料/尺寸/公差/粗糙度/设计者/校核者） |
| `载荷工况.csv` | 设计输入：四种工况载荷与安全系数要求 |
| `材料清单.csv` | BOM：零件编码、材料、规格、数量、重量 |
| `预期检查结果.json` | 自检基线：检查汇总与仿真结论的期望值 |

### 产物实体文件（上传用）

| 文件 | 类别 | 说明 |
| --- | --- | --- |
| `DRW-000_revA.dxf` | drawing | 迭代 1 概念方案总图（基线快照） |
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
- 完整基线见 `预期检查结果.json`。

## 使用方式

### 1. 载入示例数据

```bash
# 载入到 .iterd-example 数据目录（默认库 .iterd-example/iterd.db）
uv run python scripts/load_example.py --with-check --with-sim

# 指定数据目录与数据库
uv run python scripts/load_example.py --data-dir .iterd-example --with-check

# 载入指定数据集
uv run python scripts/load_example.py --dataset examples/datasets/项目-某型输送机机架结构设计
```

脚本幂等：项目/规则/规则集/仿真模板按编码或名称跳过已存在记录。
`--with-check` / `--with-sim` 会启动进程内 worker 执行规则检查与仿真并等待终态。

载入后启动服务查看：`uv run iterd serve`，默认管理员 `admin / admin123`，
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
