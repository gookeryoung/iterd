"""示例数据集载入脚本：把 examples/datasets/项目-XXX 写入 iterd（演示 / 联调 / 备份样本生成）.

数据载入逻辑在 :mod:`iterd.example_datasets`（与 ``iterd seed`` 共用），
本脚本提供独立入口：指定单个数据集、可选执行规则检查与仿真（进程内 worker）。

用法::

    uv run python scripts/load_example.py                       # 载入默认数据集
    uv run python scripts/load_example.py --with-check --with-sim  # 附带执行规则检查与仿真
    uv run python scripts/load_example.py --data-dir .iterd-example --database-url sqlite+aiosqlite:///./demo.db

数据部分幂等：项目 / 规则 / 规则集 / 模板按编码或名称跳过已存在记录，重复执行只补充缺失部分。
整体覆盖重建请直接使用 ``iterd seed``。
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = REPO_ROOT / "examples" / "datasets" / "项目-某型输送机机架结构设计"


def _build_parser() -> argparse.ArgumentParser:
    """命令行参数。"""
    parser = argparse.ArgumentParser(prog="load_example", description="载入 iterd 示例数据集")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="数据集目录路径")
    parser.add_argument("--data-dir", default=None, help="iterd 数据目录（默认 .iterd-example）")
    parser.add_argument("--database-url", default=None, help="覆盖数据库连接串")
    parser.add_argument("--with-check", action="store_true", help="载入后对绑定迭代执行规则检查")
    parser.add_argument("--with-sim", action="store_true", help="载入后按仿真模板发起作业")
    return parser


async def _wait_terminal(factory: Any, kind: str, entity_id: int) -> dict[str, Any]:
    """轮询至终态并返回最新状态（worker 异步执行）。"""
    from iterd.plugins.rules.models import CheckRun
    from iterd.plugins.simulation.models import SimJob

    model = CheckRun if kind == "check" else SimJob
    for _ in range(120):
        async with factory() as session:
            entity = await session.get(model, entity_id)
            if entity is not None and entity.status in ("succeeded", "failed"):
                return {"status": entity.status, "summary": entity.summary, "error": getattr(entity, "error", None)}
        await asyncio.sleep(0.5)
    return {"status": "timeout", "summary": None, "error": None}


async def _run_checks(factory: Any, dataset: Path, index: dict[str, Any], sets: dict[str, Any]) -> None:
    """对绑定迭代执行规则检查（进程内 worker，任务记录与界面进度一致）。"""
    from iterd.example_datasets import read_json
    from iterd.plugins.rules import services as rule_services

    bindings = read_json(dataset / "规则集.json").get("bindings", [])
    for binding in bindings:
        iteration = index["iterations"][(binding["project_code"], int(binding["iteration_number"]))]
        async with factory() as session:
            run, _task = await rule_services.create_check_run(
                session,
                actor_id=1,
                iteration_id=iteration.id,
                rule_set_id=sets[binding["rule_set_name"]].id,
            )
            await session.commit()
            run_id = run.id
        state = await _wait_terminal(factory, "check", run_id)
        print(f"检查运行 #{run_id}（迭代 {iteration.number}）：{state['status']} {state['summary']}")


async def _run_simulations(
    factory: Any,
    dataset: Path,
    index: dict[str, Any],
    templates: dict[str, Any],
    versions: dict[str, Any],
) -> None:
    """按仿真模板发起作业（绑定产物与迭代取自预期检查结果）。"""
    from iterd.example_datasets import read_json
    from iterd.plugins.simulation import services as sim_services

    expected_data = read_json(dataset / "预期检查结果.json")
    expected = {item["template_code"]: item for item in expected_data["expected_simulations"]}
    iteration = index["iterations"][
        (expected_data["iteration"]["project_code"], int(expected_data["iteration"]["number"]))
    ]
    for code, item in expected.items():
        version = versions.get(item["bind_artifact_code"])
        async with factory() as session:
            job, _task = await sim_services.create_sim_job(
                session,
                actor_id=1,
                iteration_id=iteration.id,
                template_id=templates[code].id,
                artifact_version_id=version.id if version is not None else None,
            )
            await session.commit()
            job_id = job.id
        state = await _wait_terminal(factory, "sim", job_id)
        print(f"仿真作业 #{job_id}（{code}）：{state['status']} {state['summary']} {state['error'] or ''}")


async def _load(dataset: Path, args: argparse.Namespace) -> None:
    """主载入流程。"""
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.core.migrations import upgrade_head
    from iterd.example_datasets import DEMO_USERS, load_dataset

    # 触发全部模型注册（含 simulation 与 tasks）
    from iterd.plugins import accounts, artifacts, notify, projects, rules, simulation, trace  # noqa: F401
    from iterd.plugins.accounts.services import get_by_username
    from iterd.plugins.rules import services as rule_services
    from iterd.plugins.simulation import services as sim_services
    from iterd.seed import ensure_admin
    from iterd.tasks import models as task_models  # noqa: F401
    from iterd.tasks import runner

    settings = get_settings()
    # 建库走 alembic 迁移（带 alembic_version），与 serve/seed/worker 一致；
    # create_all 会建出"当前结构但未版本化"的库，serve 启动 stamp 基线后重复加列报错
    upgrade_head(settings.database_url)
    engine = get_engine(settings.database_url)
    factory = get_session_factory(engine)
    print(f"数据库: {settings.database_url}")

    worker = None
    if args.with_check or args.with_sim:
        rule_services.register_executors()
        sim_services.register_executors()
        worker = await runner.start_in_app_worker()

    try:
        async with factory() as session:
            await ensure_admin(session, settings.admin_username, settings.admin_password)
            admin = await get_by_username(session, settings.admin_username)
            for username, (password, email) in DEMO_USERS.items():
                if await get_by_username(session, username) is None:
                    from iterd.plugins.accounts.services import create_user

                    await create_user(session, username=username, password=password, email=email)
            await session.commit()
            admin = await get_by_username(session, settings.admin_username)
            assert admin is not None
            loaded = await load_dataset(session, dataset, actor_id=admin.id)
        index, sets, templates, versions = loaded["index"], loaded["sets"], loaded["templates"], loaded["versions"]
        print(
            f"项目 {len(index['projects'])} 个 / 迭代 {len(index['iterations'])} 个 / "
            f"产物 {len(versions)} 个 / 规则 {len(loaded['rules'])} 条 / "
            f"规则集 {len(sets)} 个 / 模板 {len(templates)} 个"
        )
        print(f"用户就绪: {settings.admin_username} / {' / '.join(DEMO_USERS)}")

        if args.with_check:
            await _run_checks(factory, dataset, index, sets)
        if args.with_sim:
            await _run_simulations(factory, dataset, index, templates, versions)
    finally:
        if worker is not None:
            await runner.stop_in_app_worker(worker)
        await engine.dispose()

    print("示例数据载入完成")


def main(argv: list[str] | None = None) -> int:
    """脚本入口（环境变量须在导入 iterd.core.config 前设置）。"""
    args = _build_parser().parse_args(argv)
    data_dir = Path(args.data_dir).resolve() if args.data_dir else REPO_ROOT / ".iterd-example"
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["ITERD_DATA_DIR"] = str(data_dir)
    if args.database_url:
        os.environ["ITERD_DATABASE_URL"] = args.database_url

    from iterd.core import config as cfg
    from iterd.core import database as dbmod
    from iterd.core import storage as stmod

    dbmod.reset_database()
    stmod.reset_storage()
    cfg.reset_settings(None)

    dataset = Path(args.dataset).resolve()
    if not dataset.is_dir():
        print(f"数据集目录不存在: {dataset}", file=__import__("sys").stderr)
        return 1
    asyncio.run(_load(dataset, args))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
