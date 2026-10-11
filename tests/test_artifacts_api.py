"""artifacts API 测试：上传 / 版本 / 元数据 / 关联 / 软删."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def active_iteration(client: TestClient) -> dict[str, Any]:
    project = client.post("/api/v1/projects", json={"code": "PA", "name": "项目"}).json()
    iteration = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "迭代"}).json()
    client.patch(f"/api/v1/iterations/{iteration['id']}", json={"title": "迭代", "status": "active"})
    return iteration


def test_artifact_lifecycle(client: TestClient, active_iteration: dict[str, Any]) -> None:
    it = active_iteration["id"]
    artifact = client.post(
        f"/api/v1/artifacts?iteration_id={it}", json={"code": "B-1", "name": "支座", "category": "drawing"}
    ).json()

    v1 = client.post(
        f"/api/v1/artifacts/{artifact['id']}/versions",
        files={"file": ("B-1_revA.dwg", b"content-v1")},
        data={"metadata": '{"材料": "Q345"}', "note": "首次"},
    )
    assert v1.status_code == 201
    v2 = client.post(f"/api/v1/artifacts/{artifact['id']}/versions", files={"file": ("B-1_revB.dwg", b"content-v2")})
    assert v2.status_code == 201
    assert v2.json()["version_no"] == 2

    # 同内容去重：sha256 一致
    v3 = client.post(f"/api/v1/artifacts/{artifact['id']}/versions", files={"file": ("B-1_revB.dwg", b"content-v2")})
    assert v3.json()["sha256"] == v2.json()["sha256"]

    versions = client.get(f"/api/v1/artifacts/{artifact['id']}/versions").json()
    assert [v["version_no"] for v in versions] == [1, 2, 3]

    detail = client.get(f"/api/v1/artifacts/{artifact['id']}").json()
    assert detail["current_version_id"] == v3.json()["id"]

    downloaded = client.get(f"/api/v1/versions/{v1.json()['id']}/download")
    assert downloaded.content == b"content-v1"
    assert "attachment" in downloaded.headers["content-disposition"]

    listed = client.get("/api/v1/artifacts", params={"iteration_id": it}).json()
    assert len(listed) == 1


def test_duplicate_artifact_code(client: TestClient, active_iteration: dict[str, Any]) -> None:
    it = active_iteration["id"]
    assert (
        client.post(
            f"/api/v1/artifacts?iteration_id={it}", json={"code": "C-1", "name": "a", "category": "drawing"}
        ).status_code
        == 201
    )
    dup = client.post(f"/api/v1/artifacts?iteration_id={it}", json={"code": "C-1", "name": "b", "category": "model"})
    assert dup.status_code == 400


def test_artifact_update_and_soft_delete(client: TestClient, active_iteration: dict[str, Any]) -> None:
    it = active_iteration["id"]
    artifact = client.post(
        f"/api/v1/artifacts?iteration_id={it}", json={"code": "D-1", "name": "规范", "category": "spec"}
    ).json()
    version = client.post(
        f"/api/v1/artifacts/{artifact['id']}/versions", files={"file": ("D-1.md", b"# spec")}, data={"metadata": "{}"}
    ).json()

    updated = client.patch(
        f"/api/v1/artifacts/{artifact['id']}",
        json={"name": "技术规范", "description": "更新", "metadata": {"材料": "铝合金"}},
    )
    assert updated.status_code == 200
    version_detail = client.get(f"/api/v1/versions/{version['id']}").json()
    assert version_detail["metadata_json"] == {"材料": "铝合金"}

    deleted = client.delete(f"/api/v1/artifacts/{artifact['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/artifacts/{artifact['id']}").status_code == 404
    assert client.get("/api/v1/artifacts", params={"iteration_id": it}).json() == []


def test_artifact_links(client: TestClient, active_iteration: dict[str, Any]) -> None:
    it = active_iteration["id"]
    a = client.post(
        f"/api/v1/artifacts?iteration_id={it}", json={"code": "E-1", "name": "零件图", "category": "drawing"}
    ).json()
    b = client.post(
        f"/api/v1/artifacts?iteration_id={it}", json={"code": "E-2", "name": "装配图", "category": "model"}
    ).json()
    for aid in (a["id"], b["id"]):
        client.post(f"/api/v1/artifacts/{aid}/versions", files={"file": (f"E-{aid}.dwg", b"x")})

    link = client.post(f"/api/v1/artifacts/{a['id']}/links", json={"dst_artifact_id": b["id"], "link_type": "part_of"})
    assert link.status_code == 201
    dup = client.post(f"/api/v1/artifacts/{a['id']}/links", json={"dst_artifact_id": b["id"], "link_type": "part_of"})
    assert dup.status_code == 400
    self_link = client.post(
        f"/api/v1/artifacts/{a['id']}/links", json={"dst_artifact_id": a["id"], "link_type": "refers_to"}
    )
    assert self_link.status_code == 400
    links = client.get(f"/api/v1/artifacts/{a['id']}/links").json()
    assert len(links) == 1

    # 关联列表带出对端产物编码/名称
    assert links[0]["dst_code"] == "E-2"
    assert links[0]["dst_name"] == "装配图"
    # 反向可见（双向查询）
    assert len(client.get(f"/api/v1/artifacts/{b['id']}/links").json()) == 1

    removed = client.delete(f"/api/v1/artifacts/{a['id']}/links/{links[0]['id']}")
    assert removed.status_code == 204
    assert client.get(f"/api/v1/artifacts/{a['id']}/links").json() == []
    missing = client.delete(f"/api/v1/artifacts/{a['id']}/links/99999")
    assert missing.status_code == 404


def test_artifact_preview(client: TestClient, active_iteration: dict[str, Any]) -> None:
    it = active_iteration["id"]
    markdown_artifact = client.post(
        f"/api/v1/artifacts?iteration_id={it}", json={"code": "F-1", "name": "规范", "category": "spec"}
    ).json()
    md_version = client.post(
        f"/api/v1/artifacts/{markdown_artifact['id']}/versions",
        files={"file": ("F-1.md", b"# title")},
        data={"content_type_hint": ""},
    ).json()
    preview = client.get(f"/api/v1/versions/{md_version['id']}/preview")
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("text/markdown")
    assert "inline" in preview.headers["content-disposition"]

    # 二进制类型（content_type 由 multipart 推断为 octet-stream 时按扩展名/类型判定）
    drawing = client.post(
        f"/api/v1/artifacts?iteration_id={it}", json={"code": "F-2", "name": "图纸", "category": "drawing"}
    ).json()
    binary = client.post(
        f"/api/v1/artifacts/{drawing['id']}/versions", files={"file": ("F-2.bin", b"\x00\x01binary")}
    ).json()
    unsupported = client.get(f"/api/v1/versions/{binary['id']}/preview")
    assert unsupported.status_code == 415


def test_artifact_update_category(client: TestClient, active_iteration: dict[str, Any]) -> None:
    it = active_iteration["id"]
    artifact = client.post(
        f"/api/v1/artifacts?iteration_id={it}", json={"code": "G-1", "name": "零件", "category": "drawing"}
    ).json()
    updated = client.patch(f"/api/v1/artifacts/{artifact['id']}", json={"category": "model"})
    assert updated.status_code == 200
    assert updated.json()["category"] == "model"
    invalid = client.patch(f"/api/v1/artifacts/{artifact['id']}", json={"category": "unknown"})
    assert invalid.status_code == 422


def test_artifact_category_manual(client: TestClient, active_iteration: dict[str, Any]) -> None:
    """manual（技术说明书）类别可创建/更新，非法类别仍 422。"""
    it = active_iteration["id"]
    created = client.post(
        f"/api/v1/artifacts?iteration_id={it}", json={"code": "M-1", "name": "技术说明书", "category": "manual"}
    )
    assert created.status_code == 201, created.text
    assert created.json()["category"] == "manual"
    updated = client.patch(f"/api/v1/artifacts/{created.json()['id']}", json={"category": "manual"})
    assert updated.status_code == 200
    assert updated.json()["category"] == "manual"


def _review_scenario(client: TestClient) -> dict[str, Any]:
    """项目 + 激活迭代 + 合规/违规产物（文件名规则触发）。"""
    project = client.post("/api/v1/projects", json={"code": "RV", "name": "状态项目"}).json()
    iteration = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "迭代一"}).json()
    client.patch(f"/api/v1/iterations/{iteration['id']}", json={"title": "迭代一", "status": "active"})
    ok_art = client.post(
        f"/api/v1/artifacts?iteration_id={iteration['id']}",
        json={"code": "OK-1", "name": "合规件", "category": "drawing"},
    ).json()
    client.post(
        f"/api/v1/artifacts/{ok_art['id']}/versions",
        files={"file": ("OK-1_revA.dwg", b"ok")},
        data={"metadata": '{"材料": "Q235", "尺寸": "10", "公差": "±0.1"}'},
    )
    bad_art = client.post(
        f"/api/v1/artifacts?iteration_id={iteration['id']}",
        json={"code": "BAD-1", "name": "违规件", "category": "drawing"},
    ).json()
    client.post(
        f"/api/v1/artifacts/{bad_art['id']}/versions", files={"file": ("badname.dwg", b"bad")}, data={"metadata": "{}"}
    )
    return {"project": project, "iteration": iteration, "ok": ok_art, "bad": bad_art}


def _run_review(client: TestClient, scenario: dict[str, Any]) -> None:
    """创建单 rules 作业模板并发起运行，轮询至终态。"""
    import time

    rule = client.post(
        "/api/v1/rules",
        json={
            "code": "RV-FN",
            "name": "文件名规范",
            "category": "drafting",
            "checker_type": "filename_convention",
            "params": {"pattern": r"^[A-Z0-9-]+_rev[A-Z]\."},
            "severity_default": "error",
        },
    ).json()
    rule_set = client.post(
        "/api/v1/rule-sets",
        json={"name": "状态集", "project_id": scenario["project"]["id"], "rule_ids": [rule["id"]]},
    ).json()
    workflow = client.post(
        "/api/v1/workflows",
        json={
            "code": "RV-REVIEW",
            "name": "状态审查",
            "project_id": scenario["project"]["id"],
            "definition": f"name: 状态审查\njobs:\n  check:\n    uses: rules/check\n    with: {{rule_set: {rule_set['id']}}}\n",
        },
    ).json()
    created = client.post(
        f"/api/v1/iterations/{scenario['iteration']['id']}/workflow-runs", json={"workflow_id": workflow["id"]}
    )
    assert created.status_code == 202, created.text
    run_id = created.json()["id"]
    for _ in range(50):
        final = client.get(f"/api/v1/workflow-runs/{run_id}").json()
        if final["status"] in ("succeeded", "failed"):
            return
        time.sleep(0.2)
    pytest.fail("审查运行未在时限内结束")


def test_project_review_status(client: TestClient) -> None:
    """项目级审查状态聚合：passed / failed（含明细）/ stale / unreviewed 四态。"""
    import time as _time

    scenario = _review_scenario(client)
    project_id = scenario["project"]["id"]

    def status_of(code: str) -> dict[str, Any]:
        items = client.get(f"/api/v1/projects/{project_id}/review-status").json()
        return next(item for item in items if item["code"] == code)

    # 未跑任何检查：unreviewed
    assert status_of("OK-1")["status"] == "unreviewed"
    assert status_of("OK-1")["findings"] == []

    _run_review(client, scenario)

    ok = status_of("OK-1")
    bad = status_of("BAD-1")
    assert ok["status"] == "passed"
    assert ok["findings"] == []
    assert ok["check_run_id"] is not None
    assert bad["status"] == "failed"
    assert len(bad["findings"]) == 1
    finding = bad["findings"][0]
    assert finding["rule_code"] == "RV-FN"
    assert finding["severity"] == "error"
    assert finding["location"] == "badname.dwg"
    assert finding["version_no"] == 1

    # 上传新版本（晚于检查开始时间）→ stale
    # created_at 为数据库端秒级精度，须跨过秒边界后再上传以确保 created 秒 > started 秒
    _time.sleep(1.1)
    uploaded = client.post(
        f"/api/v1/artifacts/{scenario['bad']['id']}/versions",
        files={"file": ("BAD-1_revB.dwg", b"bad2")},
        data={"metadata": "{}"},
    )
    assert uploaded.status_code == 201
    _time.sleep(0.05)
    assert status_of("BAD-1")["status"] == "stale"

    # 新迭代产物未参与任何检查 → unreviewed
    it2 = client.post(f"/api/v1/projects/{project_id}/iterations", json={"title": "迭代二"}).json()
    client.patch(f"/api/v1/iterations/{it2['id']}", json={"title": "迭代二", "status": "active"})
    client.post(
        f"/api/v1/artifacts?iteration_id={it2['id']}",
        json={"code": "NEW-1", "name": "新件", "category": "manual"},
    )
    assert status_of("NEW-1")["status"] == "unreviewed"


def test_project_part_of_links_cycle(client: TestClient, active_iteration: dict[str, Any]) -> None:
    """项目级 part_of 边：环状关联正常返回（消费侧环安全前提），跨项目边被过滤。"""
    it = active_iteration["id"]
    project_id = active_iteration["project_id"]
    a = client.post(
        f"/api/v1/artifacts?iteration_id={it}", json={"code": "CY-A", "name": "总图A", "category": "drawing"}
    ).json()
    b = client.post(
        f"/api/v1/artifacts?iteration_id={it}", json={"code": "CY-B", "name": "零件图B", "category": "drawing"}
    ).json()
    client.post(f"/api/v1/artifacts?iteration_id={it}", json={"code": "CY-C", "name": "孤立图C", "category": "drawing"})
    for src, dst in ((a, b), (b, a)):
        created = client.post(
            f"/api/v1/artifacts/{src['id']}/links", json={"dst_artifact_id": dst["id"], "link_type": "part_of"}
        )
        assert created.status_code == 201, created.text

    # 跨项目产物关联（另一项目 D）：不得出现在本项目边集
    other_project = client.post("/api/v1/projects", json={"code": "OTH", "name": "他项目"}).json()
    other_it = client.post(f"/api/v1/projects/{other_project['id']}/iterations", json={"title": "他迭代"}).json()
    client.patch(f"/api/v1/iterations/{other_it['id']}", json={"title": "他迭代", "status": "active"})
    d = client.post(
        f"/api/v1/artifacts?iteration_id={other_it['id']}",
        json={"code": "OTH-D", "name": "外部图", "category": "drawing"},
    ).json()
    cross = client.post(f"/api/v1/artifacts/{a['id']}/links", json={"dst_artifact_id": d["id"], "link_type": "part_of"})
    assert cross.status_code == 201

    resp = client.get(f"/api/v1/projects/{project_id}/artifact-links")
    assert resp.status_code == 200
    edges = {(e["src_artifact_id"], e["dst_artifact_id"]) for e in resp.json()}
    assert edges == {(a["id"], b["id"]), (b["id"], a["id"])}

    # 环状关联下审查状态聚合正常返回（服务端无递归）
    status = client.get(f"/api/v1/projects/{project_id}/review-status")
    assert status.status_code == 200
    assert {item["code"] for item in status.json()} == {"CY-A", "CY-B", "CY-C"}
