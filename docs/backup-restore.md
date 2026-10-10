# iterd 备份还原操作手册

适用版本：iterd 0.1.0+（备份协议 manifest v1）。设计依据见 `.trae/designs/data-directory.md`，数据目录说明见 `docs/data-directory.md`。

## 1. 备份内容与归档结构

一次备份覆盖两部分数据：

- **数据库**：SQLite `iterd.db`，使用 `sqlite3.Connection.backup` 页级热备份，服务运行中可直接备份，无需停服；
- **对象存储**：`objects/` 内容寻址产物文件（可选 `--no-objects` 排除）。

归档为 `.tar.gz`，内部结构（`backup/` 为归档根前缀）：

```
iterd-backup-<软件版本>-v1-<UTC 时间戳>.tar.gz
├── backup/manifest.json     # 备份元信息：协议版本、软件版本、备份时间、逐表行数、对象统计
├── backup/data/iterd.db     # 数据库一致性快照
└── backup/objects/          # 对象存储文件（{sha256 前 2 位}/{sha256}）
```

对象存储内容寻址且版本不可变，多次备份间重复对象自然去重，重复还原同一对象为幂等覆盖。

## 2. 自动备份触发规则

| 触发方式 | 规则 | 相关配置 |
|---|---|---|
| 启动自动备份 | `iterd serve` 启动时检查 `backups/` 内最新归档，距上次备份超过间隔（默认 24 小时）才执行一次；备份失败仅记录告警，不阻断服务启动 | `ITERD_BACKUP_INTERVAL_HOURS`（0 = 关闭自动备份） |
| 手动备份 | `iterd backup` 随时执行 | 见下文命令 |
| 自动清理 | 每次备份完成后按保留上限轮换，超出部分从旧到新删除 | `ITERD_BACKUP_KEEP`（默认 30 份）；`--keep` 单次覆盖 |

备份周期策略建议：开启启动自动备份（默认），高频使用环境可配合操作系统计划任务（cron / 任务计划程序）定期调用 `iterd backup`；归档文件名含 UTC 时间戳且可按名称排序，便于外部脚本按天/周归档到异地介质。

## 3. 备份命令

```bash
# 备份到默认目录 ~/.iterd/backups（自动命名，应用保留策略）
iterd backup

# 备份到指定路径（不触发默认目录轮换）
iterd backup --output D:\backup\my.tar.gz

# 仅备份数据库，不含对象存储
iterd backup --no-objects

# 本次备份后最多保留 10 份归档
iterd backup --keep 10
```

成功输出备份归档绝对路径；失败（如数据库文件缺失）输出 `[error]` 并以退出码 1 结束。

## 4. 备份数据校验

还原前自动执行以下校验，任一失败即终止并报错：

1. 归档可读（合法 gzip/tar）；
2. `backup/manifest.json` 存在且为 JSON；
3. manifest 协议版本在支持集合内（当前仅 `v1`，跨大版本归档会明确报"不支持的备份协议版本"）；
4. `backup/data/iterd.db` 存在。

只查看归档内容不还原：

```python
from pathlib import Path
from iterd.core.backup import inspect_backup
print(inspect_backup(Path("~/.iterd/backups/iterd-backup-0.1.0-v1-20261010T121530Z.tar.gz").expanduser()))
```

还原完成后还会做**还原后校验**：逐表行数与 manifest 中记录的 `row_counts` 比对，不一致抛出 `RestoreError`（行数校验不一致），保证恢复数据零丢失。

## 5. 还原操作流程

### 5.1 完整还原（数据库 + 对象存储）

```bash
iterd restore ~/.iterd/backups/iterd-backup-0.1.0-v1-20261010T121530Z.tar.gz
```

流程：校验归档 → SQLite backup API 将备份库页级覆盖到目标 `iterd.db`（**不删除目标文件**，服务运行中也可恢复；目标不存在时自动创建）→ 解包 `objects/` 覆盖对象目录（内容寻址，同名幂等）→ 重置进程内数据库/存储单例 → 还原后行数校验。

注意：正在运行的服务进程内已持有的会话仍指向旧连接池，建议还原后重启 `iterd serve` 以确保全部连接读取恢复后的数据。

### 5.2 增量还原（多次归档叠加）

对象存储内容寻址不可变，因此跨归档"增量"天然成立——依次恢复多个归档等价于直接恢复最新归档：

```bash
# 场景：最新归档损坏或缺失某批早期对象时，先恢复基础归档，再叠加最新归档
iterd restore iterd-backup-0.1.0-v1-20261001T000000Z.tar.gz --no-objects
iterd restore iterd-backup-0.1.0-v1-20261010T000000Z.tar.gz
```

第一遍只还原数据库（`--no-objects`），第二遍完整还原；对象目录按内容哈希覆盖，不会产生重复文件。数据库以最后一次恢复的归档为准。

### 5.3 指定时间点还原

归档文件名含 UTC 时间戳且可排序，选定目标时间点之前**最近**的一份归档恢复即可：

```bash
# 列出可用归档（按时间排序）
ls ~/.iterd/backups

# 回到 2026-10-08 当天末尾的状态：选择时间戳 ≤ 目标时点的最新归档
iterd restore ~/.iterd/backups/iterd-backup-0.1.0-v1-20261008T235900Z.tar.gz
```

秒级时间点恢复（基于 WAL 归档）当前版本未实现，恢复粒度为归档时间点；对更细粒度有要求的部署应缩短备份间隔（`ITERD_BACKUP_INTERVAL_HOURS`）。

## 6. 异常处理

| 现象 | 原因 | 处理方案 |
|---|---|---|
| `备份失败: SQLite 数据库文件不存在` | database_url 指向的库尚未创建 | 先 `iterd seed` 或启动一次服务建库 |
| `还原失败: 备份归档不可读` | 归档损坏或传输不完整 | 重新传输；源介质损坏则改用次新归档 |
| `还原失败: 不支持的备份协议版本` | 归档由更高版本 iterd 生成 | 升级 iterd 后重试；manifest 版本向前不兼容时需按升级说明迁移 |
| `还原失败: 归档缺少数据库文件` | 归档被人为修改或缺成员 | 换用其他归档 |
| `还原失败: 还原后行数校验不一致` | 归档在备份后被篡改 | 换用其他归档，不要采信该归档 |
| `默认备份目录不可用` 告警 | `backups/` 不可写（权限/磁盘） | 程序自动降级到系统临时目录并告警；修复权限后用 `--output` 指定目录 |
| 服务运行中还原后数据未刷新 | 进程内连接池持旧连接 | 重启 `iterd serve` |

## 7. 保留与清理

- 默认保留最近 30 份归档（`ITERD_BACKUP_KEEP`），每次通过默认目录备份后自动轮换；
- 需要更长的合规保留期时，将 `backups/` 归档同步到外部介质后调低本地保留数量；
- 手工删除归档不影响系统运行；删除全部归档后下一次启动自动备份会重新生成。
