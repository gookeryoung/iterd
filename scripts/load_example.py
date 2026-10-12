"""示例数据集载入脚本：把 examples/datasets/项目-XXX 写入 iterd（演示 / 联调 / 备份样本生成）.

数据载入逻辑在 :mod:`iterd.example_datasets`（与 ``iterd seed`` 共用），
本脚本提供独立入口：指定单个数据集、可选提交迭代方案触发审查流水线（进程内 worker）。

用法::

    uv run python scripts/load_example.py                  # 仅载入数据
    uv run python scripts/load_example.py --with-review    # 载入后按审查模板 runs 节提交方案并等待终态
    uv run python scripts/load_example.py --data-dir .iterd-example --database-url sqlite+aiosqlite:///./demo.db

数据部分幂等：项目 / 规则 / 规则集 / 模板按编码或名称跳过已存在记录，重复执行只补充缺失部分；
``--with-review`` 每次执行均会新增一次提交方案（runs 每次提交都产生新的运行结果）。
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
    parser.add_argument(
        "--with-review",
        action="store_true",
        help="载入后按审查模板 runs 节提交迭代方案，触发审查流水线并等待终态",
    )
    return parser


async def _wait_terminal(factory: Any, run_id: int) -> dict[str, Any]:
    """轮询审查运行至终态或会签挂起并返回最新状态（in-app worker 异步执行）."""
    from iterd.plugins.workflows.models import WorkflowRun

    for _ in range(240):
        async with factory() as session:
            run = await session.get(WorkflowRun, run_id)
            if run is not None and run.status in ("succeeded", "failed", "waiting"):
                # waiting：审批会签作业挂起，待办中心签署后由界面续跑
                return {"status": run.status, "summary": run.summary}
        await asyncio.sleep(0.5)
    return {"status": "timeout", "summary": None}


async def _print_run_jobs(factory: Any, run_id: int) -> None:
    """打印运行内各作业结论：规则作业输出 CheckRun summary，仿真作业输出 verdict。"""
    from iterd.plugins.rules.models import CheckRun
    from iterd.plugins.simulation.models import SimJob
    from iterd.plugins.workflows.models import WorkflowJob

    async with factory() as session:
        jobs = list(
            (
                await session.execute(
                    WorkflowJob.__table__.select().where(WorkflowJob.run_id == run_id).order_by(WorkflowJob.order_index)
                )
            ).mappings()
        )
        for job in jobs:
            name = job["name"] or job["job_key"]
            if job["check_run_id"] is not None:
                check_run = await session.get(CheckRun, int(job["check_run_id"]))
                summary = dict(check_run.summary or {}) if check_run is not None else {}
                print(
                    f"    {name}: {summary.get('error', 0)} error / {summary.get('warning', 0)} warning / "
                    f"{summary.get('info', 0)} info（产物 {summary.get('artifacts', 0)} / 规则 {summary.get('rules', 0)}）"
                )
            elif job["sim_job_id"] is not None:
                sim_job = await session.get(SimJob, int(job["sim_job_id"]))
                if sim_job is None:
                    print(f"    {name}: 仿真作业缺失")
                    continue
                summary = dict(sim_job.summary or {})
                raw_failures = summary.get("failures") or []
                failed_keys: list[str] = []
                if isinstance(raw_failures, list):
                    failed_keys = [item["key"] for item in raw_failures if isinstance(item, dict) and "key" in item]
                # else: 计数形态（超阈指标数），无明细键
                print(
                    f"    {name}: {sim_job.status} verdict={summary.get('verdict', '-')}"
                    + (
                        f" failed_keys={failed_keys}"
                        if failed_keys
                        else (f" failures={raw_failures}" if isinstance(raw_failures, int) and raw_failures else "")
                    )
                )
            else:
                print(f"    {name}: {job['status']}")


async def _run_review(factory: Any, dataset: Path) -> None:
    """按审查模板 runs 节定位迭代并提交方案（进程内 worker 执行，轮询至终态）。"""
    from iterd.core.config import get_settings
    from iterd.example_datasets import read_yaml
    from iterd.plugins.accounts.services import get_by_username
    from iterd.plugins.workflows import services as workflow_services

    path = dataset / "审查模板.yaml"
    if not path.is_file():
        print("数据集无 审查模板.yaml，跳过审查提交")
        return
    runs = read_yaml(path).get("runs", [])
    if not runs:
        print("审查模板.yaml 无 runs 节，跳过审查提交")
        return

    settings = get_settings()
    submissions: dict[tuple[str, int], list[int]] = {}
    async with factory() as session:
        admin = await get_by_username(session, settings.admin_username)
        assert admin is not None
        for run in runs:
            from iterd.plugins.projects import services as project_services

            project = next(
                (p for p in await project_services.list_projects(session) if p.code == run["project_code"]), None
            )
            assert project is not None, f"项目不存在: {run['project_code']}"
            iterations = await project_services.list_iterations(session, project.id)
            iteration = next((it for it in iterations if it.number == int(run["iteration_number"])), None)
            assert iteration is not None, f"迭代不存在: {run['project_code']} #{run['iteration_number']}"
            key = (run["project_code"], int(run["iteration_number"]))
            if key in submissions:
                continue
            submission, created = await workflow_services.create_submission(
                session,
                actor_id=int(admin.id),
                iteration_id=int(iteration.id),
                title=f"示例提交（{run['project_code']} 迭代 {run['iteration_number']}）",
                note="load_example --with-review 预置提交",
            )
            await session.commit()
            submissions[key] = [int(r.id) for r in created]
            print(
                f"提交方案 #{submission.id}（{run['project_code']} 迭代 {run['iteration_number']}）：{len(created)} 条运行"
            )

    for (project_code, number), run_ids in submissions.items():
        for run_id in run_ids:
            state = await _wait_terminal(factory, run_id)
            summary = state["summary"] or {}
            print(
                f"  审查运行 #{run_id}（{project_code} 迭代 {number}）：{state['status']} "
                f"conclusion={summary.get('conclusion', '-')}"
            )
            await _print_run_jobs(factory, run_id)


async def _load(dataset: Path, args: argparse.Namespace) -> None:
    """主载入流程。"""
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.core.migrations import upgrade_head
    from iterd.example_datasets import DEMO_USERS, load_dataset

    # 触发全部模型注册（含 simulation 与 tasks）
    from iterd.plugins import accounts, artifacts, bom, notify, projects, rules, simulation, trace, workflows  # noqa: F401
    from iterd.plugins.accounts.services import get_by_username
    from iterd.plugins.workflows import services as workflow_services
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
    if args.with_review:
        workflow_services.register_executors()
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
        workflows = loaded["workflows"]
        bom = loaded.get("bom", {})
        print(
            f"项目 {len(index['projects'])} 个 / 迭代 {len(index['iterations'])} 个 / "
            f"产物 {len(versions)} 个 / 规则 {len(loaded['rules'])} 条 / "
            f"规则集 {len(sets)} 个 / 模板 {len(templates)} 个 / 审查模板 {len(workflows)} 个 / "
            f"BOM 行 {bom.get('total', 0)} 条"
        )
        print(f"用户就绪: {settings.admin_username} / {' / '.join(DEMO_USERS)}")

        if args.with_review:
            await _run_review(factory, dataset)
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
