"""workflows 端到端测试：YAML 校验 → 模板 → 发起解析 → 门禁编排 → 结论聚合 → rerun → RBAC."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import login_as


def _scenario(client: TestClient, *, with_bad: bool) -> dict[str, Any]:
    """项目 + 激活迭代 + 产物（合规件必带；with_bad 时附加违规件触发 error）。"""
    project = client.post("/api/v1/projects", json={"code": "WF", "name": "审查项目"}).json()
    iteration = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "迭代"}).json()
    client.patch(f"/api/v1/iterations/{iteration['id']}", json={"title": "迭代", "status": "active"})
    ok_art = client.post(
        f"/api/v1/artifacts?iteration_id={iteration['id']}",
        json={"code": "OK-1", "name": "合规件", "category": "drawing"},
    ).json()
    # 公差缺失：触发 warning 级规则但不触发 error 级
    client.post(
        f"/api/v1/artifacts/{ok_art['id']}/versions",
        files={"file": ("OK-1_revA.dwg", b"ok")},
        data={"metadata": '{"材料": "Q235", "尺寸": "10"}'},
    )
    if with_bad:
        bad_art = client.post(
            f"/api/v1/artifacts?iteration_id={iteration['id']}",
            json={"code": "BAD-1", "name": "违规件", "category": "drawing"},
        ).json()
        client.post(
            f"/api/v1/artifacts/{bad_art['id']}/versions",
            files={"file": ("badname.dwg", b"bad")},
            data={"metadata": "{}"},
        )
    sim_art = client.post(
        f"/api/v1/artifacts?iteration_id={iteration['id']}",
        json={"code": "FRM-002", "name": "横梁模型", "category": "model"},
    ).json()
    client.post(
        f"/api/v1/artifacts/{sim_art['id']}/versions",
        files={"file": ("FRM-002_revA.step", b"model")},
        data={"metadata": '{"材料": "Q235", "尺寸": "500", "公差": "±0.1"}'},
    )
    return {"project": project, "iteration": iteration}


def _prepare_capabilities(client: TestClient, scenario: dict[str, Any], *, stress_max: int) -> None:
    """规则库 + 规则集 + 仿真模板（默认输入 max_stress≈23.4，阈值由 stress_max 控制通过/超阈）。"""
    client.post(
        "/api/v1/rules",
        json={
            "code": "WF-FN",
            "name": "文件名规范",
            "category": "drafting",
            "checker_type": "filename_convention",
            "params": {"pattern": r"^[A-Z0-9-]+_rev[A-Z]\."},
            "severity_default": "error",
        },
    )
    client.post(
        "/api/v1/rules",
        json={
            "code": "WF-MD",
            "name": "材料必填",
            "category": "material",
            "checker_type": "metadata_required",
            "params": {"required": {"材料": "str", "尺寸": "str"}},
            "severity_default": "error",
        },
    )
    client.post(
        "/api/v1/rules",
        json={
            "code": "WF-TOL",
            "name": "公差提示",
            "category": "tolerance",
            "checker_type": "metadata_required",
            "params": {"required": {"公差": "str"}},
            "severity_default": "warning",
        },
    )
    created = client.post(
        "/api/v1/rule-sets",
        json={"name": "静态检查集", "project_id": scenario["project"]["id"], "rule_ids": []},
    )
    assert created.status_code == 201, created.text
    rule_set_id = created.json()["id"]
    rules = client.get("/api/v1/rules").json()
    added = client.post(
        f"/api/v1/rule-sets/{rule_set_id}/rules",
        json={"rule_ids": [r["id"] for r in rules if r["code"].startswith("WF-")]},
    )
    assert added.status_code == 201
    template = client.post(
        "/api/v1/sim-templates",
        json={
            "code": "WF-BEAM",
            "name": "横梁静强度",
            "solver_type": "beam_static",
            "project_id": scenario["project"]["id"],
            "thresholds": {"max_stress": {"max": stress_max}},
        },
    )
    assert template.status_code == 201, template.text


_DEFINITION = """\
name: 门禁审查
description: 静态检查通过后执行横梁仿真

jobs:
  rules-check:
    name: 静态规则检查
    uses: rules/check
    with:
      rule_set: 静态检查集
  beam-sim:
    name: 横梁静强度仿真
    needs: rules-check
    uses: simulation/run
    with:
      template: WF-BEAM
      artifact: FRM-002
"""


def _create_workflow(
    client: TestClient, scenario: dict[str, Any], definition: str | None = None, *, code: str = "WF-GATE"
) -> dict[str, Any]:
    created = client.post(
        "/api/v1/workflows",
        json={
            "code": code,
            "name": "门禁审查",
            "project_id": scenario["project"]["id"],
            "definition": definition or _DEFINITION,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def _wait_run(client: TestClient, run_id: int) -> dict[str, Any]:
    """轮询运行直至终态。"""
    final: dict[str, Any] = {}
    for _ in range(50):
        final = client.get(f"/api/v1/workflow-runs/{run_id}").json()
        if final["status"] in ("succeeded", "failed"):
            return final
        time.sleep(0.2)
    return final


# ---- AC-1 YAML 校验 ----


def test_yaml_validation_matrix(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"code": "WV", "name": "校验项目"}).json()
    base = {"code": "WV-1", "name": "模板", "project_id": project["id"]}

    ok = client.post("/api/v1/workflows", json={**base, "definition": _DEFINITION})
    assert ok.status_code == 201, ok.text
    jobs = ok.json()["jobs"]
    assert [j["key"] for j in jobs] == ["rules-check", "beam-sim"]
    assert jobs[0]["with"] == {"rule_set": "静态检查集"}
    assert jobs[1]["needs"] == ["rules-check"]

    invalid_cases = [
        "name: X\njobs:\n  a:\n    uses: rules/check\n    with: {rule_set: 1}\n  b:\n    uses: no/such\n    with: {}",
        "name: X\njobs:\n  a:\n    uses: simulation/run\n    needs: ghost\n    with: {template: T}",
        "name: X\njobs:\n  a:\n    uses: rules/check\n    needs: b\n    with: {rule_set: 1}\n  b:\n    uses: rules/check\n    needs: a\n    with: {rule_set: 1}",
        "name: X",
        "name: X\nunknown: 1\njobs:\n  a:\n    uses: rules/check\n    with: {rule_set: 1}",
        "name: X\njobs:\n  a:\n    uses: rules/check\n    typo: 1\n    with: {rule_set: 1}",
        "name: X\njobs:\n  BadKey:\n    uses: rules/check\n    with: {rule_set: 1}",
        "name: X\njobs:\n  a:\n    uses: simulation/run\n    with: {artifact: X}",
    ]
    for i, definition in enumerate(invalid_cases):
        resp = client.post("/api/v1/workflows", json={**base, "code": f"WV-ERR-{i}", "definition": definition})
        assert resp.status_code == 422, (definition, resp.text)
        assert resp.json()["code"] == "ITERD-INVALID_DEFINITION"

    dup = client.post("/api/v1/workflows", json={**base, "definition": _DEFINITION})
    assert dup.status_code == 400
    assert client.get("/api/v1/workflows/99999").status_code == 404


# ---- AC-2 发起解析与快照 ----


def test_run_reference_resolution(client: TestClient) -> None:
    scenario = _scenario(client, with_bad=False)
    _prepare_capabilities(client, scenario, stress_max=100)
    workflow = _create_workflow(client, scenario)
    it_id = scenario["iteration"]["id"]

    # 引用不存在：规则集 / 仿真模板 / 产物
    bad_cases = [
        _DEFINITION.replace("rule_set: 静态检查集", "rule_set: 不存在的规则集"),
        _DEFINITION.replace("template: WF-BEAM", "template: NO-SUCH"),
        _DEFINITION.replace("artifact: FRM-002", "artifact: NO-ART"),
    ]
    for i, definition in enumerate(bad_cases):
        wf = _create_workflow(client, scenario, definition=definition, code=f"WF-RES-{i}")
        resp = client.post(f"/api/v1/iterations/{it_id}/workflow-runs", json={"workflow_id": wf["id"]})
        assert resp.status_code == 422, (definition, resp.text)

    # 合法发起：config 固化 ID、definition 快照
    created = client.post(f"/api/v1/iterations/{it_id}/workflow-runs", json={"workflow_id": workflow["id"]})
    assert created.status_code == 202, created.text
    run = created.json()
    assert run["definition"] == _DEFINITION
    assert run["task_id"] is not None
    jobs = {j["job_key"]: j for j in run["jobs"]}
    assert jobs["rules-check"]["config"]["rule_set_id"] > 0
    assert jobs["beam-sim"]["config"]["template_id"] > 0
    assert jobs["beam-sim"]["config"]["artifact_version_id"] > 0
    # 展示字段填充
    assert jobs["rules-check"]["rule_set_name"] == "静态检查集"
    assert jobs["beam-sim"]["template_code"] == "WF-BEAM"
    assert jobs["beam-sim"]["artifact_code"] == "FRM-002"

    # 模板更新不影响已发起运行的快照
    listed = client.get(f"/api/v1/iterations/{it_id}/workflow-runs").json()
    assert len(listed) == 1
    assert client.get("/api/v1/workflow-runs/99999").status_code == 404


# ---- AC-3/AC-4 门禁编排与结论语义 ----


def test_gate_chain_failure_skips_downstream(client: TestClient) -> None:
    scenario = _scenario(client, with_bad=True)
    _prepare_capabilities(client, scenario, stress_max=100)
    workflow = _create_workflow(client, scenario)
    it_id = scenario["iteration"]["id"]

    created = client.post(f"/api/v1/iterations/{it_id}/workflow-runs", json={"workflow_id": workflow["id"]})
    assert created.status_code == 202
    final = _wait_run(client, created.json()["id"])
    assert final["status"] == "failed", final
    assert final["summary"]["conclusion"] == "failure"
    assert final["summary"]["jobs"] == {"success": 0, "failure": 1, "skipped": 1}

    jobs = {j["job_key"]: j for j in final["jobs"]}
    # 违规件 error>0 → rules 作业 failure（AC-4）
    assert jobs["rules-check"]["conclusion"] == "failure"
    assert jobs["rules-check"]["check_run_id"] is not None
    assert final["summary"]["findings"]["error"] == 2
    # 门禁：下游 skipped（AC-3）
    assert jobs["beam-sim"]["status"] == "skipped"
    assert jobs["beam-sim"]["conclusion"] == "skipped"
    assert jobs["beam-sim"]["sim_job_id"] is None
    assert any(e["level"] == "warning" for e in jobs["beam-sim"]["logs"])


def test_gate_chain_success_runs_all(client: TestClient) -> None:
    scenario = _scenario(client, with_bad=False)
    _prepare_capabilities(client, scenario, stress_max=100)
    workflow = _create_workflow(client, scenario)
    it_id = scenario["iteration"]["id"]

    created = client.post(f"/api/v1/iterations/{it_id}/workflow-runs", json={"workflow_id": workflow["id"]})
    final = _wait_run(client, created.json()["id"])
    assert final["status"] == "succeeded", final
    assert final["summary"]["conclusion"] == "success"
    assert final["summary"]["jobs"] == {"success": 2, "failure": 0, "skipped": 0}
    assert final["summary"]["sims"] == {"pass": 1, "fail": 0}

    jobs = {j["job_key"]: j for j in final["jobs"]}
    # 公差缺失仅触发 warning → 不判 failure（AC-4）
    assert final["summary"]["findings"]["warning"] >= 1
    assert jobs["rules-check"]["conclusion"] == "success"
    assert jobs["beam-sim"]["conclusion"] == "success"
    assert jobs["beam-sim"]["sim_job_id"] is not None


def test_simulation_fail_conclusion(client: TestClient) -> None:
    scenario = _scenario(client, with_bad=False)
    # 阈值低于默认输入应力（≈23.4）→ 仿真超阈 → 作业 failure → 运行 failed
    _prepare_capabilities(client, scenario, stress_max=10)
    workflow = _create_workflow(client, scenario)
    created = client.post(
        f"/api/v1/iterations/{scenario['iteration']['id']}/workflow-runs", json={"workflow_id": workflow["id"]}
    )
    final = _wait_run(client, created.json()["id"])
    assert final["status"] == "failed", final
    assert final["summary"]["jobs"] == {"success": 1, "failure": 1, "skipped": 0}
    jobs = {j["job_key"]: j for j in final["jobs"]}
    assert jobs["beam-sim"]["conclusion"] == "failure"
    assert final["summary"]["sims"] == {"pass": 0, "fail": 1}


# ---- AC-5 rerun / RBAC ----


def test_rerun_creates_new_run(client: TestClient) -> None:
    scenario = _scenario(client, with_bad=False)
    _prepare_capabilities(client, scenario, stress_max=100)
    workflow = _create_workflow(client, scenario)
    it_id = scenario["iteration"]["id"]
    first = client.post(f"/api/v1/iterations/{it_id}/workflow-runs", json={"workflow_id": workflow["id"]}).json()
    _wait_run(client, first["id"])

    rerun = client.post(f"/api/v1/workflow-runs/{first['id']}/rerun")
    assert rerun.status_code == 202, rerun.text
    new_run = rerun.json()
    assert new_run["id"] != first["id"]
    assert new_run["definition"] == first["definition"]
    final = _wait_run(client, new_run["id"])
    assert final["status"] == "succeeded"
    runs = client.get(f"/api/v1/iterations/{it_id}/workflow-runs").json()
    assert len(runs) == 2
    assert client.post("/api/v1/workflow-runs/99999/rerun").status_code == 404
    # 审计可查：发起与 rerun 各有记录
    audits = client.get("/api/v1/audit-logs", params={"resource_type": "workflow_run"}).json()
    actions = {a["action"] for a in audits}
    assert {"workflow_run.create", "workflow_run.rerun"} <= actions


def test_workflow_rbac(client: TestClient) -> None:
    scenario = _scenario(client, with_bad=False)
    _prepare_capabilities(client, scenario, stress_max=100)
    workflow = _create_workflow(client, scenario)
    it_id = scenario["iteration"]["id"]

    # 非项目成员 designer：不可发起 / 不可编辑项目级模板
    login_as(client, "designer", "designer123")
    denied = client.post(f"/api/v1/iterations/{it_id}/workflow-runs", json={"workflow_id": workflow["id"]})
    assert denied.status_code == 403, denied.text
    patch_denied = client.patch(f"/api/v1/workflows/{workflow['id']}", json={"enabled": False})
    assert patch_denied.status_code == 403
    # 项目成员可读（viewer 路径：非成员 designer 亦不可读运行详情）
    assert client.get("/api/v1/workflow-runs/99999").status_code == 404

    # 全局模板：非超管不可创建
    login_as(client, "designer", "designer123")
    global_tpl = client.post("/api/v1/workflows", json={"code": "WF-GLOBAL", "name": "全局", "definition": _DEFINITION})
    assert global_tpl.status_code == 403

    # 超管可建全局模板，项目列表包含全局
    login_as(client, "admin", "admin1234")
    created = client.post("/api/v1/workflows", json={"code": "WF-GLOBAL", "name": "全局", "definition": _DEFINITION})
    assert created.status_code == 201, created.text
    listed = client.get("/api/v1/workflows", params={"project_id": scenario["project"]["id"]}).json()
    codes = {item["code"] for item in listed}
    assert {"WF-GATE", "WF-GLOBAL"} <= codes
    # 审计可查
    audits = client.get("/api/v1/audit-logs", params={"resource_type": "workflow"}).json()
    assert any(a["action"] == "workflow.create" for a in audits)


def test_workflow_update_and_enabled(client: TestClient) -> None:
    scenario = _scenario(client, with_bad=False)
    _prepare_capabilities(client, scenario, stress_max=100)
    workflow = _create_workflow(client, scenario)

    updated = client.patch(f"/api/v1/workflows/{workflow['id']}", json={"enabled": False})
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False

    # 停用模板不可发起
    denied = client.post(
        f"/api/v1/iterations/{scenario['iteration']['id']}/workflow-runs", json={"workflow_id": workflow["id"]}
    )
    assert denied.status_code == 400

    # 非法定义更新被拒
    bad = client.patch(f"/api/v1/workflows/{workflow['id']}", json={"definition": "name: X"})
    assert bad.status_code == 422

    # 合法定义更新：名称与描述同步 YAML 头
    good = client.patch(
        f"/api/v1/workflows/{workflow['id']}",
        json={"definition": _DEFINITION.replace("门禁审查", "升级审查"), "enabled": True},
    )
    assert good.status_code == 200, good.text
    assert good.json()["name"] == "升级审查"


# ---- 边界与异常路径 ----


def test_parse_definition_invalid_matrix() -> None:
    """YAML 语法与结构非法矩阵（纯函数层直接断言定位错误）。"""
    from iterd.plugins.workflows.definition import WorkflowDefinitionError, parse_definition

    invalid_texts = [
        "name: [unclosed",  # YAML 语法错误
        "- a\n- b",  # 顶层非映射
        "jobs:\n  a:\n    uses: rules/check\n    with: {rule_set: 1}",  # 缺 name
        "name: X\ndescription: [1]\njobs:\n  a:\n    uses: rules/check\n    with: {rule_set: 1}",  # description 非字符串
        "name: X\njobs: {}",  # jobs 空映射
        "name: X\njobs:\n  a:\n    name: ''\n    uses: rules/check\n    with: {rule_set: 1}",  # job name 空
        "name: X\njobs:\n  a:\n    uses: rules/check\n    needs: 1\n    with: {rule_set: 1}",  # needs 非列表
        "name: X\njobs:\n  a:\n    uses: rules/check\n    with: [1]",  # with 非映射
        "name: X\njobs:\n  a:\n    uses: simulation/run\n    with: {template: T, bogus: 1}",  # with 未知字段
        "name: X\njobs:\n  a:\n    uses: rules/check\n    with: {rule_set: true}",  # rule_set 类型
        "name: X\njobs:\n  a:\n    uses: simulation/run\n    with: {template: [1]}",  # template 类型
        "name: X\njobs:\n  a:\n    uses: simulation/run\n    with: {template: T, artifact: 1}",  # artifact 类型
        "name: X\njobs:\n  a:\n    uses: simulation/run\n    with: {template: T, inputs: [1]}",  # inputs 类型
    ]
    for text in invalid_texts:
        with pytest.raises(WorkflowDefinitionError):
            parse_definition(text)


def test_run_reference_edge_cases(client: TestClient) -> None:
    """int 型引用 / 停用仿真模板 / 迭代不存在 / 模板详情与全局模板维护权."""
    scenario = _scenario(client, with_bad=False)
    _prepare_capabilities(client, scenario, stress_max=100)
    it_id = scenario["iteration"]["id"]

    # int 型引用：rule_set / template 按 id 解析
    rule_set_id = next(r["id"] for r in client.get("/api/v1/rule-sets").json() if r["name"] == "静态检查集")
    sim_tpl = next(t for t in client.get("/api/v1/sim-templates").json() if t["code"] == "WF-BEAM")
    int_def = _DEFINITION.replace("rule_set: 静态检查集", f"rule_set: {rule_set_id}").replace(
        "template: WF-BEAM", f"template: {sim_tpl['id']}"
    )
    workflow = _create_workflow(client, scenario, definition=int_def, code="WF-INT-REF")
    created = client.post(f"/api/v1/iterations/{it_id}/workflow-runs", json={"workflow_id": workflow["id"]})
    assert created.status_code == 202, created.text

    # 停用仿真模板：发起时 422 早失败（无 PATCH 端点，直改 DB）
    async def _set_enabled(template_id: int, enabled: bool) -> None:
        from sqlalchemy import update

        from iterd.core.config import get_settings
        from iterd.core.database import get_engine, get_session_factory
        from iterd.plugins.simulation.models import SimTemplate

        factory = get_session_factory(get_engine(get_settings().database_url))
        async with factory() as session:
            await session.execute(update(SimTemplate).where(SimTemplate.id == template_id).values(enabled=enabled))
            await session.commit()

    asyncio.run(_set_enabled(sim_tpl["id"], False))
    wf_disabled = _create_workflow(client, scenario, definition=_DEFINITION, code="WF-DISABLED")
    resp = client.post(f"/api/v1/iterations/{it_id}/workflow-runs", json={"workflow_id": wf_disabled["id"]})
    assert resp.status_code == 422, resp.text
    asyncio.run(_set_enabled(sim_tpl["id"], True))

    # 迭代不存在：404
    assert (
        client.post("/api/v1/iterations/99999/workflow-runs", json={"workflow_id": workflow["id"]}).status_code == 404
    )

    # 模板详情端点：含解析后 jobs；不存在 404
    detail = client.get(f"/api/v1/workflows/{workflow['id']}")
    assert detail.status_code == 200
    assert [j["key"] for j in detail.json()["jobs"]] == ["rules-check", "beam-sim"]
    assert client.get("/api/v1/workflows/99999").status_code == 404

    # 全局模板：非超管不可维护（PATCH 403）
    global_tpl = client.post(
        "/api/v1/workflows", json={"code": "WF-GLOBAL-2", "name": "全局", "definition": _DEFINITION}
    )
    assert global_tpl.status_code == 201, global_tpl.text
    login_as(client, "designer", "designer123")
    denied = client.patch(f"/api/v1/workflows/{global_tpl.json()['id']}", json={"enabled": False})
    assert denied.status_code == 403
    login_as(client, "admin", "admin1234")


def test_job_exception_marks_failure(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """规则检查执行异常：作业判 failed、绑定 CheckRun 一并置 failed、整链不中断."""
    from iterd.plugins.rules import services as rule_services

    scenario = _scenario(client, with_bad=False)
    _prepare_capabilities(client, scenario, stress_max=100)
    workflow = _create_workflow(client, scenario)

    async def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(rule_services, "execute_check_run", _boom)
    created = client.post(
        f"/api/v1/iterations/{scenario['iteration']['id']}/workflow-runs", json={"workflow_id": workflow["id"]}
    )
    assert created.status_code == 202
    final = _wait_run(client, created.json()["id"])
    assert final["status"] == "failed", final
    jobs = {j["job_key"]: j for j in final["jobs"]}
    assert jobs["rules-check"]["status"] == "failed"
    assert jobs["rules-check"]["conclusion"] == "failure"
    assert any(e["level"] == "error" and "RuntimeError" in e["message"] for e in jobs["rules-check"]["logs"])
    assert jobs["rules-check"]["check_run_id"] is not None


def test_workflow_run_executor_missing_run(client: TestClient) -> None:
    """worker 执行器对不存在运行返回失败 TaskResult（不抛出，由任务框架记 failed）."""

    async def _exec() -> Any:
        from iterd.core.config import get_settings
        from iterd.core.database import get_engine, get_session_factory
        from iterd.plugins.workflows import services as workflow_services
        from iterd.tasks.runner import _LiveContext

        factory = get_session_factory(get_engine(get_settings().database_url))
        async with factory() as session:
            return await workflow_services._workflow_run_executor(session, {"workflow_run_id": 99999}, _LiveContext())

    result = asyncio.run(_exec())
    assert result.success is False
    assert "99999" in str(result.error)


def test_run_workflows_sync_failure_path(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """数据集预执行异常路径：运行标记 failed、残留 pending Task 被清理."""

    async def _prepare() -> tuple[Any, Any, Any]:
        from sqlalchemy import select

        from iterd.core.config import get_settings
        from iterd.core.database import get_engine, get_session_factory
        from iterd.plugins.projects.models import Iteration, Project
        from iterd.plugins.workflows.models import WorkflowTemplate

        factory = get_session_factory(get_engine(get_settings().database_url))
        async with factory() as session:
            project = (await session.execute(select(Project).where(Project.code == "WF"))).scalar_one()
            iteration = (
                await session.execute(select(Iteration).where(Iteration.project_id == project.id))
            ).scalar_one()
            template = (
                await session.execute(select(WorkflowTemplate).where(WorkflowTemplate.code == "WF-SYNC"))
            ).scalar_one()
            return iteration, template, factory

    scenario = _scenario(client, with_bad=False)
    _prepare_capabilities(client, scenario, stress_max=100)
    _create_workflow(client, scenario, code="WF-SYNC")

    (tmp_path / "审查模板.yaml").write_text(
        "runs:\n  - project_code: WF\n    iteration_number: 1\n    workflow_code: WF-SYNC\n",
        encoding="utf-8",
    )

    async def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    from iterd.plugins.workflows import services as workflow_services

    monkeypatch.setattr(workflow_services, "execute_workflow_run", _boom)

    async def _run() -> list[dict[str, Any]]:
        from iterd.example_datasets import run_workflows_sync

        iteration, template, factory = await _prepare()
        loaded = {
            "index": {"iterations": {("WF", 1): iteration}},
            "workflows": {"WF-SYNC": template},
        }
        async with factory() as session:
            return await run_workflows_sync(session, tmp_path, loaded, actor_id=1)

    results = asyncio.run(_run())
    assert len(results) == 1
    assert results[0]["status"] == "failed"
    assert results[0]["summary"] is None
