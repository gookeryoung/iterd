# iterd 生产镜像：Python 3.12 + uv 安装（含前端构建产物 src/iterd/static）
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先装依赖（层缓存，依赖不变不重装）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 装项目本体（src/ 含同源托管的静态 SPA）
COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# 数据目录（SQLite 与内容寻址存储挂载点）
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8000

# 默认启动 API（compose 中 app 侧关闭内置 worker，由独立 worker 服务承担）
CMD ["uv", "run", "--no-dev", "iterd", "serve"]
