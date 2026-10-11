"""示例数据集载入脚本：把 examples/datasets/项目-XXX 写入 iterd（演示 / 联调 / 备份样本生成）。

用法::

    uv run python scripts/load_example.py                       # 载入默认数据集
    uv run python scripts/load_example.py --with-check --with-sim  # 附带执行规则检查与仿真
    uv run python scripts/load_example.py --data-dir .iterd-example --database-url sqlite+aiosqlite:///./demo.db

幂等：项目 / 规则 / 规则集 / 模板按编码或名称跳过已存在记录，重复执行只补充缺失部分。
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = REPO_ROOT / "examples" / "datasets" / "项目-某型输送机机架结构设计"

# 产物扩展名 → 上传时的 content_type（存储与预览类型解析用）
CONTENT_TYPES = {
    ".dxf": "application/dxf",
    ".dwg": "application/acad",
    ".step": "application/step",
    ".stp": "application/step",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
}

# 迭代状态机推进路径（planned -> active -> closed）
_STATUS_PATH = {"planned": [], "active": ["active"], "closed": ["active", "closed"]}

# 演示用户（与 seed.py 的 designer 口令保持一致）
DEMO_USERS = {
    "designer": ("designer123", "designer@iterd.local"),
    "reviewer": ("reviewer123", "reviewer@iterd.local"),
}


def _build_parser() -> argparse.ArgumentParser:
    """命令行参数。"""
    parser = argparse.ArgumentParser(prog="load_example", description="载入 iterd 示例数据集")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="数据集目录路径")
    parser.add_argument("--data-dir", default=None, help="iterd 数据目录（默认 .iterd-example）")
    parser.add_argument("--database-url", default=None, help="覆盖数据库连接串")
    parser.add_argument("--with-check", action="store_true", help="载入后对绑定迭代执行规则检查")
    parser.add_argument("--with-sim", action="store_true", help="载入后按仿真模板发起作业")
    return parser


def _read_json(path: Path) -> dict[str, Any]:
    """读取数据集 JSON 文件（utf-8-sig 兼容 Excel 导出的 BOM）。"""
    return json.loads(path.read_text(encoding="utf-8-sig"))  # type: ignore[no-any-return]


def _read_csv(path: Path) -> list[dict[str, str]]:
    """读取数据集 CSV 文件（utf-8-sig，首行为表头）。"""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _as_date(value: str | None) -> date | None:
    """YYYY-MM-DD 字符串转 date（空值返回 None）。"""
    return date.fromisoformat(value) if value else None


def _guess_content_type(filename: str) -> str:
    """按扩展名推断 content_type。"""
    return CONTENT_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


def _coerce_literal(value: str) -> str | int | float | bool:
    """CSV 字面量类型推断：true/false → bool，其余依次尝试 int、float，失败保留字符串。

    metadata_required 检查器按类型校验元数据，而 CSV 读出的值恒为字符串，
    需先按字面量推断类型，规则中的 number / bool 校验才有意义。
    """
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    for cast in (int, float):
        try:
            return cast(value)  # type: ignore[arg-type]
        except ValueError:
            continue
    return value


async def _ensure_users(session: Any, settings: Any) -> Any:
    """确保管理员与演示用户存在，返回管理员。"""
    from iterd.plugins.accounts.services import create_user, get_by_username
    from iterd.seed import ensure_admin

    await ensure_admin(session, settings.admin_username, settings.admin_password)
    admin = await get_by_username(session, settings.admin_username)
    for username, (password, email) in DEMO_USERS.items():
        if await get_by_username(session, username) is None:
            await create_user(session, username=username, password=password, email=email)
    await session.commit()
    print(f"用户就绪: {settings.admin_username} / {' / '.join(DEMO_USERS)}")
    return admin


async def _load_structure(session: Any, dataset: Path, actor_id: int) -> dict[str, Any]:
    """载入项目 / 子项目 / 成员 / 迭代 / 基线，返回编码索引。"""
    from iterd.plugins.projects import services as project_services

    data = _read_json(dataset / "项目结构.json")
    index: dict[str, Any] = {
        "projects": {},  # code -> Project
        "iterations": {},  # (project_code, number) -> Iteration
        "baselines": [],
    }

    root = data["project"]
    existing = {p.code: p for p in await project_services.list_projects(session)}
    project = existing.get(root["code"])
    if project is None:
        project = await project_services.create_project(
            session,
            actor_id=actor_id,
            parent_id=None,
            code=root["code"],
            name=root["name"],
            description=root["description"],
            status=root.get("status", "active"),
        )
    index["projects"][root["code"]] = project

    for sub in data.get("sub_projects", []):
        if sub["code"] in existing:
            index["projects"][sub["code"]] = existing[sub["code"]]
            continue
        index["projects"][sub["code"]] = await project_services.create_project(
            session,
            actor_id=actor_id,
            parent_id=index["projects"][sub["parent_code"]].id,
            code=sub["code"],
            name=sub["name"],
            description=sub["description"],
            status=sub.get("status", "active"),
        )
    await session.commit()

    for member in data.get("members", []):
        from iterd.plugins.accounts.services import get_by_username

        user = await get_by_username(session, member["username"])
        if user is None:
            print(f"跳过成员 {member['username']}（用户不存在）")
            continue
        await project_services.upsert_member(
            session,
            actor_id=actor_id,
            project_id=index["projects"][member["project_code"]].id,
            user_id=user.id,
            role=member["role"],
        )

    for item in data.get("iterations", []):
        project = index["projects"][item["project_code"]]
        number = int(item["number"])
        iterations = await project_services.list_iterations(session, project.id)
        iteration = next((it for it in iterations if it.number == number), None)
        if iteration is None:
            iteration = await project_services.create_iteration(
                session,
                actor_id=actor_id,
                project_id=project.id,
                title=item["title"],
                objective=item["objective"],
                start_date=_as_date(item.get("start_date")),
                end_date=_as_date(item.get("end_date")),
                number=number,
            )
        for status in _STATUS_PATH.get(item.get("status", "planned"), []):
            if iteration.status != status:
                await project_services.update_iteration(
                    session, actor_id=actor_id, iteration=iteration, fields={"status": status}
                )
        index["iterations"][(item["project_code"], number)] = iteration
    await session.commit()

    for item in data.get("baselines", []):
        iteration = index["iterations"][(item["project_code"], int(item["iteration_number"]))]
        baselines = await project_services.list_baselines(session, iteration.id)
        if any(b.name == item["name"] for b in baselines):
            continue
        index["baselines"].append(
            await project_services.create_baseline(
                session, actor_id=actor_id, iteration_id=iteration.id, name=item["name"]
            )
        )
    await session.commit()
    print(f"项目 {len(index['projects'])} 个 / 迭代 {len(index['iterations'])} 个 / 基线 {len(index['baselines'])} 条")
    return index


async def _load_artifacts(session: Any, dataset: Path, index: dict[str, Any], actor_id: int) -> dict[str, Any]:
    """载入产物与版本（含元数据），返回编码索引。"""
    from iterd.plugins.artifacts import services as artifact_services

    metadata_rows = {row["产物编码"]: row for row in _read_csv(dataset / "产物元数据.csv")}
    created: dict[str, Any] = {}
    for row in _read_csv(dataset / "产物清单.csv"):
        iteration = index["iterations"][(row["项目编码"], int(row["迭代序号"]))]
        project = index["projects"][row["项目编码"]]
        artifact = await artifact_services.create_artifact(
            session,
            actor_id=actor_id,
            project_id=project.id,
            iteration_id=iteration.id,
            code=row["产物编码"],
            name=row["产物名称"],
            category=row["类别"],
            description=row.get("备注", ""),
        )
        file_path = dataset / row["文件名"]
        metadata: dict[str, object] = {
            k: _coerce_literal(v) for k, v in metadata_rows.get(row["产物编码"], {}).items() if v and k != "产物编码"
        }
        version = await artifact_services.upload_version(
            session,
            actor_id=actor_id,
            artifact=artifact,
            filename=row["文件名"],
            content_type=_guess_content_type(row["文件名"]),
            stream=io.BytesIO(file_path.read_bytes()),
            metadata=metadata,
            note=row.get("备注", ""),
        )
        created[row["产物编码"]] = version
    await session.commit()
    print(f"产物 {len(created)} 个（含版本各 1 个）")
    return created


async def _load_rules(session: Any, dataset: Path, actor_id: int) -> dict[str, Any]:
    """载入规则库，返回 code -> id 索引。"""
    from iterd.plugins.rules import services as rule_services

    rules = {r.code: r for r in await rule_services.list_rules(session)}
    for item in _read_json(dataset / "规则库.json")["rules"]:
        if item["code"] in rules:
            continue
        rules[item["code"]] = await rule_services.create_rule(
            session,
            actor_id=actor_id,
            code=item["code"],
            name=item["name"],
            category=item["category"],
            checker_type=item["checker_type"],
            params=item.get("params"),
            severity_default=item.get("severity_default", "warning"),
            enabled=item.get("enabled", True),
            description=item.get("description", ""),
        )
    await session.commit()
    print(f"规则 {len(rules)} 条")
    return rules


async def _load_rule_sets(
    session: Any, dataset: Path, index: dict[str, Any], rules: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    """载入规则集与迭代绑定，返回 name -> id 索引。"""
    from iterd.plugins.rules import services as rule_services

    data = _read_json(dataset / "规则集.json")
    sets = {rs.name: rs for rs in await rule_services.list_rule_sets(session)}
    for item in data["rule_sets"]:
        project_id = index["projects"][item["project_code"]].id if item.get("project_code") else None
        rule_ids = [rules[code].id for code in item["rule_codes"] if code in rules]
        if item["name"] in sets:
            await rule_services.set_rule_set_rules(session, rule_set_id=sets[item["name"]].id, rule_ids=rule_ids)
            continue
        sets[item["name"]] = await rule_services.create_rule_set(
            session,
            actor_id=actor_id,
            project_id=project_id,
            name=item["name"],
            description=item.get("description", ""),
            rule_ids=rule_ids,
        )
    for binding in data.get("bindings", []):
        iteration = index["iterations"][(binding["project_code"], int(binding["iteration_number"]))]
        await rule_services.bind_rule_set(
            session,
            actor_id=actor_id,
            rule_set_id=sets[binding["rule_set_name"]].id,
            iteration_id=iteration.id,
        )
    await session.commit()
    print(f"规则集 {len(sets)} 个 / 绑定 {len(data.get('bindings', []))} 条")
    return sets


async def _load_sim_templates(session: Any, dataset: Path, index: dict[str, Any], actor_id: int) -> dict[str, Any]:
    """载入仿真模板，返回 code -> id 索引。"""
    from iterd.plugins.simulation import services as sim_services

    templates = {t.code: t for t in await sim_services.list_templates(session)}
    for item in _read_json(dataset / "仿真模板.json")["templates"]:
        if item["code"] in templates:
            continue
        templates[item["code"]] = await sim_services.create_template(
            session,
            actor_id=actor_id,
            code=item["code"],
            name=item["name"],
            solver_type=item["solver_type"],
            project_id=index["projects"][item["project_code"]].id if item.get("project_code") else None,
            params=item.get("params"),
            thresholds=item.get("thresholds"),
            description=item.get("description", ""),
        )
    await session.commit()
    print(f"仿真模板 {len(templates)} 个")
    return templates


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


async def _run_checks(factory: Any, dataset: Path, index: dict[str, Any], sets: dict[str, Any], actor_id: int) -> None:
    """对绑定迭代执行规则检查。"""
    from iterd.plugins.rules import services as rule_services

    bindings = _read_json(dataset / "规则集.json").get("bindings", [])
    for binding in bindings:
        iteration = index["iterations"][(binding["project_code"], int(binding["iteration_number"]))]
        async with factory() as session:
            run, _task = await rule_services.create_check_run(
                session,
                actor_id=actor_id,
                iteration_id=iteration.id,
                rule_set_id=sets[binding["rule_set_name"]].id,
            )
            await session.commit()
            run_id = run.id
        state = await _wait_terminal(factory, "check", run_id)
        print(f"检查运行 #{run_id}（迭代 {iteration.number}）：{state['status']} {state['summary']}")


async def _run_simulations(  # noqa: PLR0913, PLR0917 - 载入参数
    factory: Any,
    dataset: Path,
    index: dict[str, Any],
    templates: dict[str, Any],
    versions: dict[str, Any],
    actor_id: int,
) -> None:
    """按仿真模板发起作业（绑定产物与迭代取自预期检查结果）。"""
    from iterd.plugins.simulation import services as sim_services

    expected_data = _read_json(dataset / "预期检查结果.json")
    expected = {item["template_code"]: item for item in expected_data["expected_simulations"]}
    iteration = index["iterations"][
        (expected_data["iteration"]["project_code"], int(expected_data["iteration"]["number"]))
    ]
    for code, item in expected.items():
        version = versions.get(item["bind_artifact_code"])
        async with factory() as session:
            job, _task = await sim_services.create_sim_job(
                session,
                actor_id=actor_id,
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
    from iterd.models import Base

    # 触发全部模型注册（含 simulation 与 tasks）
    from iterd.plugins import accounts, artifacts, notify, projects, rules, simulation, trace  # noqa: F401
    from iterd.plugins.rules import services as rule_services
    from iterd.plugins.simulation import services as sim_services
    from iterd.tasks import models as task_models  # noqa: F401
    from iterd.tasks import runner

    settings = get_settings()
    engine = get_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = get_session_factory(engine)
    print(f"数据库: {settings.database_url}")

    worker = None
    if args.with_check or args.with_sim:
        rule_services.register_executors()
        sim_services.register_executors()
        worker = await runner.start_in_app_worker()

    try:
        async with factory() as session:
            admin = await _ensure_users(session, settings)
            index = await _load_structure(session, dataset, admin.id)
            versions = await _load_artifacts(session, dataset, index, admin.id)
            rules_index = await _load_rules(session, dataset, admin.id)
            sets = await _load_rule_sets(session, dataset, index, rules_index, admin.id)
            templates = await _load_sim_templates(session, dataset, index, admin.id)

        if args.with_check:
            await _run_checks(factory, dataset, index, sets, admin.id)
        if args.with_sim:
            await _run_simulations(factory, dataset, index, templates, versions, admin.id)
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
