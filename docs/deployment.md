# iterd 单机部署与运维手册

适用场景：单台服务器上以 SQLite 为数据库部署 iterd（默认形态）。设计说明见 `docs/data-directory.md`（数据目录）与 `docs/backup-restore.md`（备份还原）。

## 1. 快速部署

```bash
# 1. 安装（wheel 包含前端构建产物，无需 Node 环境）
pip install iterd

# 2. 初始化数据库并创建初始管理员与演示数据（首次部署）
iterd seed

# 3. 启动服务（同源托管前端，默认 0.0.0.0:8000）
iterd serve
```

浏览器访问 `http://<服务器地址>:8000`，使用初始管理员账号登录（`ITERD_ADMIN_USERNAME` / `ITERD_ADMIN_PASSWORD`，默认 `admin` / `admin1234`，生产环境务必通过配置修改）。

## 2. 配置项

全部配置项均可用 `ITERD_` 前缀环境变量覆盖，也可写入 `~/.iterd/config/.env`。单机部署常用项：

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `ITERD_DATA_DIR` | `~/.iterd` | 数据根目录整体覆盖（子目录与默认数据库路径一并切换） |
| `ITERD_DATABASE_URL` | `sqlite+aiosqlite:///~/.iterd/data/iterd.db` | 数据库连接串；单机保持 SQLite，多机/高并发切 PostgreSQL |
| `ITERD_SQLITE_BUSY_TIMEOUT_MS` | `5000` | SQLite 写锁等待上限（毫秒），多进程并发写时适当调大 |
| `ITERD_TASK_WORKER_IN_APP` | `true` | 任务 worker 内置于 API 进程；独立 worker 部署时设 `false` |
| `ITERD_SECRET_KEY` | `change-me-in-production` | JWT 签名密钥，生产环境必须替换为强随机值 |
| `ITERD_HOST` / `ITERD_PORT` | `0.0.0.0` / `8000` | 服务监听地址与端口 |
| `ITERD_BACKUP_INTERVAL_HOURS` | `24` | 启动自动备份间隔（小时），0 关闭 |
| `ITERD_BACKUP_KEEP` | `30` | 备份目录最大保留归档数 |

## 3. SQLite 并发与多进程部署

iterd 默认对 SQLite 连接启用 **WAL 模式**并注入 **busy_timeout**（默认 5000ms，可经 `ITERD_SQLITE_BUSY_TIMEOUT_MS` 调整）。WAL 允许读写并发，busy_timeout 让并发写入方在锁冲突时排队等待而非立即报错，缓解多进程写锁冲突。

单机多进程形态（API 进程 + 独立 worker）：

```bash
# API 进程：关闭内置 worker
ITERD_TASK_WORKER_IN_APP=false iterd serve

# 独立 worker 进程（可起多个，任务队列公平抢占）
iterd worker
```

运维建议：

- 单机并发量低（<10 人团队）时保持默认内置 worker 即可；
- 多 worker 或高频流水线运行时，若日志出现 `database is locked`，优先调大 `ITERD_SQLITE_BUSY_TIMEOUT_MS`（如 10000）；
- 数据规模或并发持续增长时，迁移到 PostgreSQL（设置 `ITERD_DATABASE_URL` 后重启，建表自动执行），备份还原相关能力届时以数据库自身方案为准。

## 4. 备份策略

- **自动备份**：`iterd serve` 启动时距上次备份超过 `ITERD_BACKUP_INTERVAL_HOURS`（默认 24 小时）自动执行一次，失败仅告警不阻断启动；
- **手动备份**：`iterd backup` 随时执行；产物文件较多时用增量备份降低体积——先保留一份全量归档作基线，日常用 `iterd backup --base <全量归档>` 只打包新增对象（数据库始终为全量快照）；
- **还原**：`iterd restore <归档>` 完整还原；增量归档还原须同时传 `--base <同一基线>`。详细操作与异常处理见《备份还原操作手册》（docs/backup-restore.md）；
- **异地容灾**：定期将 `backups/` 归档同步到外部介质（rsync / 对象存储 CLI 均可），归档文件名含 UTC 时间戳可直接排序。

## 5. 日常运维清单

| 事项 | 频率 | 操作 |
|---|---|---|
| 检查自动备份是否成功 | 每日 | 查看 `~/.iterd/logs/` 日志与 `backups/` 最新归档时间 |
| 异地同步备份归档 | 每周 | 同步 `backups/` 到外部介质 |
| 还原演练 | 每月 | 在测试目录（`ITERD_DATA_DIR` 指向临时目录）执行一次 `iterd restore` 并抽查数据 |
| 磁盘空间检查 | 每周 | `tmp/`、`cache/` 可随时清空；备份占用大则调低 `ITERD_BACKUP_KEEP` |
| 日志清理 | 按需 | 清理 `logs/` 历史日志，应用重启后自动重建 |
| 版本升级 | 按需 | 升级前先 `iterd backup`；升级后按发布说明执行迁移，破坏性迁移见备份手册升级警示 |

## 6. 常见问题

| 现象 | 处理方案 |
|---|---|
| 并发写入报 `database is locked` | 调大 `ITERD_SQLITE_BUSY_TIMEOUT_MS`；仍频繁出现则迁移 PostgreSQL |
| 还原后页面数据未刷新 | 重启 `iterd serve`（进程内连接池持旧连接） |
| 忘记管理员口令 | 重新执行 `iterd seed` 前先备份；或按配置中 `ITERD_ADMIN_USERNAME`/`ITERD_ADMIN_PASSWORD` 重建初始账号 |
| 端口被占用 | 修改 `ITERD_PORT` 或释放端口后重启 |
| 服务迁移到新机器 | 拷贝整个 `~/.iterd` 目录，或备份归档 + `iterd restore`（见 docs/data-directory.md） |
