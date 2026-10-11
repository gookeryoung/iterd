# iterd

> 产品迭代式开发系统.

[![PyPI](https://img.shields.io/pypi/v/iterd)](https://pypi.org/project/iterd/)
[![CI](https://github.com/gookeryoung/iterd/actions/workflows/ci.yml/badge.svg)](https://github.com/gookeryoung/iterd/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Coverage](https://img.shields.io/badge/coverage-%E2%89%A595%25-brightgreen.svg)

## 特性

- **构建工具链**：hatchling + uv + ruff + pyrefly + pytest + coverage
- **Python 版本**：3.12 ~ 3.12
- **代码质量**：pre-commit 钩子 + ruff lint/format，覆盖率阈值 95%
- **CI/CD**：GitHub Actions（lint + typecheck + 多版本测试 + 自动发布到 PyPI）
- **文档**：Sphinx + ReadTheDocs（中文 zh_CN）
- **多版本测试**：tox + tox-uv（py312）
- **容器化**：Dockerfile（含国内镜像源配置）
- **Web 框架**：FastAPI + uvicorn
- **项目结构**：src layout + py.typed 类型标记

## 安装

```bash
pip install iterd
```

或使用 [uv](https://docs.astral.sh/uv/)：

```bash
uv add iterd
```

## 快速上手

```python
import iterd

print(iterd.__version__)
```

## 开发

```bash
# 安装开发依赖
uv sync --extra dev

# 运行测试（含覆盖率，阈值 95%）
uv run pytest -m "not slow" --cov=iterd --cov-fail-under=95

# 类型检查
uv run pyrefly check .

# 代码风格
uv run ruff check src tests
uv run ruff format --check src tests
```

### Make 快捷命令

项目提供 Makefile 封装常用操作，运行 `make help` 查看全部命令：

```bash
make sync     # 安装开发依赖
make check    # 全套门禁 (lint + typecheck + cov)
make build    # 构建分发包
make clean    # 清理构建产物
make bump patch  # 版本号 bump
```

### 前端开发与构建（dev / build / serve）

前端位于 `frontend/`（Vite + React + TypeScript + AntD，pnpm 管理），后端 FastAPI 同源托管构建产物。三个 CLI 命令覆盖完整开发链路（对标 cndb 前端工程化体系）：

```bash
# 开发模式：同时启动后端（uvicorn --reload，端口 8000）与前端（vite 热更新，端口 5173）
# 浏览器访问 http://127.0.0.1:5173，/api 与 /ws 由 Vite 代理转发到后端，Ctrl+C 一键停止全部服务
iterd dev

# 构建前端：tsc 类型检查 + vite build，产物输出到 src/iterd/static/（随 wheel 分发）
iterd build

# 生产预览：uvicorn 启动并同源托管 static/ 构建产物，根路径即前端首页，SPA 路由回退
iterd serve
```

约定：后端 dev 默认端口 8000 须与 `frontend/vite.config.ts` 的代理目标一致；无构建产物时 `iterd serve` 根路径返回 JSON 健康检查。`make build` 会先执行前端构建再打包 wheel。


## 文档

- [数据目录结构说明](docs/data-directory.md)：`~/.iterd` 数据根目录与子目录职责、权限与维护要求
- [备份还原操作手册](docs/backup-restore.md)：备份策略、`iterd backup` / `iterd restore` 操作与异常处理

文档由 Sphinx 构建，托管在 ReadTheDocs：

```bash
# 本地构建文档
make doc
```


## 多版本测试

使用 tox 在多个 Python 版本（py312）下运行测试：

```bash
make tox
```

## 许可证

MIT
