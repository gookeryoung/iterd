"""E2E 后端一键启动（供 Playwright webServer 使用）。

流程：数据目录隔离（.e2e-data，绝不触碰用户 ~/.iterd）→ seed 注入演示数据
→ 启动后端 :8000。前置：前端已构建到 src/iterd/static（make frontend-build）。
跨平台（Windows/macOS/Linux），替代 bash/PowerShell 脚本。
"""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404 - E2E 脚本需调用 uv 管理后端进程
import sys
from pathlib import Path


def main() -> int:
    # 定位项目根目录（scripts/ → frontend/ → 项目根）
    root = Path(__file__).resolve().parent.parent.parent
    os.chdir(root)

    port = os.environ.get("E2E_PORT", "8000")

    # ── 数据目录隔离 ──
    # 通过 ITERD_DATA_DIR 把数据库/对象存储/日志等整体重定向到仓库内 .e2e-data，
    # 与用户真实数据（~/.iterd）完全隔离：测试的增删改不会污染用户数据，
    # 用户数据也不会破坏 seed 后的稳定假设（如项目 id=1 为"演示项目"）。
    e2e_data = root / ".e2e-data"
    if e2e_data.exists():
        shutil.rmtree(e2e_data)  # 每轮全量重建，防 objects 等残留累积
    os.environ["ITERD_DATA_DIR"] = str(e2e_data)
    print(f"[e2e-server] 数据目录隔离: {e2e_data}", flush=True)

    print("[e2e-server] seed 演示数据...", flush=True)
    seed = subprocess.run(  # nosec B603 B607 - 命令为固定常量，uv 来自 PATH
        ["uv", "run", "iterd", "seed"],
        check=False,
        cwd=root,
    )
    if seed.returncode != 0:
        print(f"[e2e-server] seed 失败 (exit={seed.returncode})", file=sys.stderr, flush=True)
        return seed.returncode

    print(f"[e2e-server] 启动后端 http://127.0.0.1:{port} ...", flush=True)
    # exec 语义：serve 阻塞运行，Playwright 以进程退出感知服务生命周期
    return subprocess.call(  # nosec B603 B607 - 命令为固定常量，uv 来自 PATH
        ["uv", "run", "iterd", "serve", "--host", "127.0.0.1", "--port", port],
        cwd=root,
    )


if __name__ == "__main__":
    sys.exit(main())
