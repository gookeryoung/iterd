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
