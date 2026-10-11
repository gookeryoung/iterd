"""典型案例数据集载入：examples/datasets/项目-XXX → iterd 业务对象.

供 ``iterd seed``（覆盖重建后载入全部典型案例并预执行审查流水线）与
``scripts/load_example.py``（单独载入指定数据集）共用。
数据部分按编码/名称查重跳过既有记录，幂等；examples/ 仅存在于源码仓库，
wheel 安装形态下 :func:`datasets_root` 返回 None，调用方据此跳过。
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

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
STATUS_PATH = {"planned": [], "active": ["active"], "closed": ["active", "closed"]}

# 演示用户（与 seed.py 的演示口令保持一致）
DEMO_USERS = {
    "designer": ("designer123", "designer@iterd.local"),
    "reviewer": ("reviewer123", "reviewer@iterd.local"),
}


def repo_root() -> Path:
    """源码仓库根目录（src layout：src/iterd/example_datasets.py → 仓库根）."""
    return Path(__file__).resolve().parents[2]


def datasets_root() -> Path | None:
    """典型案例数据集根目录（examples/datasets）；非源码仓库返回 None."""
    root = repo_root() / "examples" / "datasets"
    return root if root.is_dir() else None


def list_datasets() -> list[Path]:
    """全部典型案例数据集目录（按名称排序）。"""
    root = datasets_root()
    if root is None:
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / "项目结构.json").is_file())


def read_json(path: Path) -> dict[str, Any]:
    """读取数据集 JSON 文件（utf-8-sig 兼容 Excel 导出的 BOM）。"""
    return json.loads(path.read_text(encoding="utf-8-sig"))  # type: ignore[no-any-return]


def read_csv(path: Path) -> list[dict[str, str]]:
    """读取数据集 CSV 文件（utf-8-sig，首行为表头）。"""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def read_yaml(path: Path) -> dict[str, Any]:
    """读取数据集 YAML 文件（utf-8-sig；审查模板.yaml 用）。"""
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))  # type: ignore[no-any-return]


def _as_date(value: str | None) -> date | None:
    """YYYY-MM-DD 字符串转 date（空值返回 None）。"""
    return date.fromisoformat(value) if value else None


def guess_content_type(filename: str) -> str:
    """按扩展名推断 content_type。"""
    return CONTENT_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


def coerce_literal(value: str) -> str | int | float | bool:
    """CSV 字面量类型推断：true/false → bool，其余依次尝试 int、float，失败保留字符串.

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


async def load_structure(session: AsyncSession, dataset: Path, actor_id: int) -> dict[str, Any]:
    """载入项目 / 子项目 / 成员 / 迭代，返回编码索引。"""
    from iterd.plugins.accounts.services import get_by_username
    from iterd.plugins.projects import services as project_services

    data = read_json(dataset / "项目结构.json")
    index: dict[str, Any] = {
        "projects": {},  # code -> Project
        "iterations": {},  # (project_code, number) -> Iteration
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
        proj = index["projects"][item["project_code"]]
        number = int(item["number"])
        iterations = await project_services.list_iterations(session, proj.id)
        iteration = next((it for it in iterations if it.number == number), None)
        if iteration is None:
            iteration = await project_services.create_iteration(
                session,
                actor_id=actor_id,
                project_id=proj.id,
                title=item["title"],
                objective=item["objective"],
                start_date=_as_date(item.get("start_date")),
                end_date=_as_date(item.get("end_date")),
                number=number,
            )
        for status in STATUS_PATH.get(item.get("status", "planned"), []):
            if iteration.status != status:
                await project_services.update_iteration(
                    session, actor_id=actor_id, iteration=iteration, fields={"status": status}
                )
        index["iterations"][(item["project_code"], number)] = iteration
    await session.commit()
    return index


async def load_artifacts(session: AsyncSession, dataset: Path, index: dict[str, Any], actor_id: int) -> dict[str, Any]:
    """载入产物与版本（含元数据），返回编码索引。"""
    from iterd.plugins.artifacts import services as artifact_services

    metadata_rows = {row["产物编码"]: row for row in read_csv(dataset / "产物元数据.csv")}
    created: dict[str, Any] = {}
    for row in read_csv(dataset / "产物清单.csv"):
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
            k: coerce_literal(v) for k, v in metadata_rows.get(row["产物编码"], {}).items() if v and k != "产物编码"
        }
        version = await artifact_services.upload_version(
            session,
            actor_id=actor_id,
            artifact=artifact,
            filename=row["文件名"],
            content_type=guess_content_type(row["文件名"]),
            stream=io.BytesIO(file_path.read_bytes()),
            metadata=metadata,
            note=row.get("备注", ""),
        )
        created[row["产物编码"]] = version
    await session.commit()
    return created


async def load_rules(session: AsyncSession, dataset: Path, actor_id: int) -> dict[str, Any]:
    """载入规则库，返回 code -> id 索引。"""
    from iterd.plugins.rules import services as rule_services

    rules = {r.code: r for r in await rule_services.list_rules(session)}
    for item in read_json(dataset / "规则库.json")["rules"]:
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
    return rules


async def load_rule_sets(
    session: AsyncSession, dataset: Path, index: dict[str, Any], rules: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    """载入规则集，返回 name -> id 索引。"""
    from iterd.plugins.rules import services as rule_services

    data = read_json(dataset / "规则集.json")
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
    await session.commit()
    return sets


async def load_sim_templates(
    session: AsyncSession, dataset: Path, index: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    """载入仿真模板，返回 code -> id 索引。"""
    from iterd.plugins.simulation import services as sim_services

    templates = {t.code: t for t in await sim_services.list_templates(session)}
    for item in read_json(dataset / "仿真模板.json")["templates"]:
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
    return templates


async def load_workflows(session: AsyncSession, dataset: Path, index: dict[str, Any], actor_id: int) -> dict[str, Any]:
    """载入审查模板（审查模板.yaml，可选文件），返回 code -> 模板索引。"""
    from iterd.plugins.workflows import services as workflow_services

    path = dataset / "审查模板.yaml"
    if not path.is_file():
        return {}
    templates = {t.code: t for t in await workflow_services.list_templates(session)}
    for item in read_yaml(path).get("templates", []):
        if item["code"] in templates:
            continue
        templates[item["code"]] = await workflow_services.create_template(
            session,
            actor_id=actor_id,
            project_id=index["projects"][item["project_code"]].id if item.get("project_code") else None,
            code=item["code"],
            name=item["name"],
            description=item.get("description", ""),
            definition=item["definition"],
            enabled=item.get("enabled", True),
        )
    await session.commit()
    return templates


async def load_dataset(session: AsyncSession, dataset: Path, *, actor_id: int) -> dict[str, Any]:
    """载入单个数据集的数据部分（项目/迭代/产物/规则/规则集/模板/审查模板），返回索引字典。"""
    index = await load_structure(session, dataset, actor_id)
    versions = await load_artifacts(session, dataset, index, actor_id)
    rules = await load_rules(session, dataset, actor_id)
    sets = await load_rule_sets(session, dataset, index, rules, actor_id)
    templates = await load_sim_templates(session, dataset, index, actor_id)
    workflows = await load_workflows(session, dataset, index, actor_id)
    return {
        "index": index,
        "versions": versions,
        "rules": rules,
        "sets": sets,
        "templates": templates,
        "workflows": workflows,
    }


async def run_workflows_sync(
    session: AsyncSession, dataset: Path, loaded: dict[str, Any], *, actor_id: int
) -> list[dict[str, Any]]:
    """按数据集 runs 绑定同步执行审查流水线（seed 预置展示用，与 worker 同一执行路径）。

    同步执行产生的调度 Task 在执行后删除，避免 serve 启动 worker 后重复执行
    （workflow 重跑会新建 CheckRun/SimJob，与 check_run 幂等重跑不同）。
    """
    from iterd.plugins.workflows import services as workflow_services
    from iterd.plugins.workflows.models import WorkflowRun
    from iterd.tasks.models import Task

    path = dataset / "审查模板.yaml"
    if not path.is_file():
        return []
    index, templates = loaded["index"], loaded["workflows"]
    results: list[dict[str, Any]] = []
    for run in read_yaml(path).get("runs", []):
        iteration = index["iterations"][(run["project_code"], int(run["iteration_number"]))]
        workflow_run, task = await workflow_services.create_workflow_run(
            session,
            actor_id=actor_id,
            iteration_id=iteration.id,
            template_id=templates[run["workflow_code"]].id,
        )
        run_id = int(workflow_run.id)
        task_id = int(task.id)
        try:
            summary = await workflow_services.execute_workflow_run(session, run_id=run_id)
            results.append(
                {
                    "workflow_run_id": run_id,
                    "workflow": run["workflow_code"],
                    "status": "succeeded" if summary["conclusion"] == "success" else "failed",
                    "summary": summary,
                }
            )
        except Exception as exc:
            await session.rollback()
            failed = await session.get(WorkflowRun, run_id)
            if failed is not None:
                failed.status = "failed"
                failed.finished_at = datetime.now(UTC)
                await session.commit()
            results.append(
                {"workflow_run_id": run_id, "workflow": run["workflow_code"], "status": "failed", "summary": None}
            )
            print(f"审查运行 #{run_id} 执行失败: {exc}")
        stale = await session.get(Task, task_id)
        if stale is not None and stale.status == "pending":
            await session.delete(stale)
            await session.commit()
    return results


async def load_all_cases(session: AsyncSession, *, actor_id: int) -> list[dict[str, Any]]:
    """载入全部典型案例（数据 + 同步预执行审查流水线），返回逐数据集摘要。

    典型案例更新后重跑 ``iterd seed`` 即整体覆盖重建，新数据立即在界面展示。
    """
    results: list[dict[str, Any]] = []
    for dataset in list_datasets():
        loaded = await load_dataset(session, dataset, actor_id=actor_id)
        workflows = await run_workflows_sync(session, dataset, loaded, actor_id=actor_id)
        results.append(
            {
                "name": dataset.name,
                "projects": len(loaded["index"]["projects"]),
                "iterations": len(loaded["index"]["iterations"]),
                "artifacts": len(loaded["versions"]),
                "workflows": workflows,
            }
        )
    return results
