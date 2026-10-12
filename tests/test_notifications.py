"""notifications 端到端测试：站内信 CRUD / 渠道扩展点 / 域事件触达 / WebSocket 推送。"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import login_as

_APPROVAL_DEF = """\
name: 会签通知演练
description: 静态检查通过后人工会签（通知联动）

jobs:
  rules-check:
    name: 静态规则检查
    uses: rules/check
    with:
      rule_set: 静态检查集
  sign-off:
    name: 总师会签
    needs: rules-check
    uses: approval/request
    with:
      approvers: [chief]
      min_count: 1
"""


def _scenario(client: TestClient) -> dict[str, Any]:
    """项目 + 激活迭代 + 合规产物（静态检查全绿，推进到审批挂起）。"""
    project = client.post("/api/v1/projects", json={"code": "NT", "name": "通知项目"}).json()
    iteration = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "迭代"}).json()
    client.patch(f"/api/v1/iterations/{iteration['id']}", json={"title": "迭代", "status": "active"})
    art = client.post(
        f"/api/v1/artifacts?iteration_id={iteration['id']}",
        json={"code": "OK-1", "name": "合规件", "category": "drawing"},
    ).json()
    client.post(
        f"/api/v1/artifacts/{art['id']}/versions",
        files={"file": ("OK-1_revA.dwg", b"ok")},
        data={"metadata": '{"材料": "Q235", "尺寸": "10"}'},
    )
    return {"project": project, "iteration": iteration}


def _prepare(client: TestClient, scenario: dict[str, Any]) -> int:
    """规则库 + 规则集 + 仿真模板（返回模板 id；全绿仿真 max_stress 放宽）。"""
    client.post(
        "/api/v1/rules",
        json={
            "code": "NT-FN",
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
            "code": "NT-MD",
            "name": "材料必填",
            "category": "material",
            "checker_type": "metadata_required",
            "params": {"required": {"材料": "str", "尺寸": "str"}},
            "severity_default": "error",
        },
    )
    rule_set = client.post(
        "/api/v1/rule-sets",
        json={"name": "静态检查集", "rule_ids": [r["id"] for r in client.get("/api/v1/rules").json()]},
    ).json()
    sim_template = client.post(
        "/api/v1/sim-templates",
        json={
            "code": "NT-BEAM",
            "name": "横梁静强度",
            "solver_type": "beam_static",
            "thresholds": {"max_stress": {"max": 10000}},
        },
    ).json()
    assert rule_set["id"] > 0 and sim_template["id"] > 0
    return int(rule_set["id"])


def _create_workflow(client: TestClient, scenario: dict[str, Any]) -> dict[str, Any]:
    """创建含审批作业的审查模板。"""
    resp = client.post(
        "/api/v1/workflows",
        json={
            "code": "NT-APPROVAL",
            "name": "会签通知流水线",
            "project_id": scenario["project"]["id"],
            "definition": _APPROVAL_DEF,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _trigger(client: TestClient, iteration_id: int, workflow_id: int) -> dict[str, Any]:
    """发起运行（202 异步）。"""
    resp = client.post(f"/api/v1/iterations/{iteration_id}/workflow-runs", json={"workflow_id": workflow_id})
    assert resp.status_code == 202, resp.text
    return resp.json()


def _wait_run(client: TestClient, run_id: int) -> dict[str, Any]:
    """轮询运行至终态。"""
    run: dict[str, Any] = {}
    for _ in range(100):
        run = client.get(f"/api/v1/workflow-runs/{run_id}").json()
        if run["status"] in ("succeeded", "failed", "waiting"):
            return run
        time.sleep(0.2)
    return run


def _by_type(items: list[dict[str, Any]], ntype: str) -> list[dict[str, Any]]:
    """按类型过滤通知列表。"""
    return [n for n in items if n["ntype"] == ntype]


def _create_tables() -> None:
    """建表（导入全部模型保证 metadata 完整；服务层直连测试用）。"""

    async def _create() -> None:
        from iterd.core.config import get_settings
        from iterd.core.database import get_engine
        from iterd.models import Base
        from iterd.plugins import accounts, artifacts, notify, projects, rules, trace  # noqa: F401
        from iterd.tasks import models as task_models  # noqa: F401

        engine = get_engine(get_settings().database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())


def test_notification_service_crud(env: Any) -> None:
    """站内信服务：写入 / 列表 / 未读数 / 单条已读 / 全部已读 / 越权 404。"""
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.core.errors import IterdError
    from iterd.plugins.notify import list_notifications, mark_all_read, mark_read, notify, unread_count

    _create_tables()
    factory = get_session_factory(get_engine(get_settings().database_url))

    async def _run() -> None:
        async with factory() as session:
            from iterd.core.security import hash_password
            from iterd.plugins.accounts.models import User

            session.add(User(username="u1", email="", hashed_password=hash_password("x12345678"), uid="u-1"))
            session.add(User(username="u2", email="", hashed_password=hash_password("x12345678"), uid="u-2"))
            await session.commit()

            await notify(session, user_id=1, ntype="run.completed", title="t1", link="/iterations/1")
            await notify(session, user_id=1, ntype="approval.pending", title="t2", project_id=9)
            await notify(session, user_id=2, ntype="run.completed", title="other")
            assert await unread_count(session, user_id=1) == 2

            items = await list_notifications(session, user_id=1)
            assert [i.title for i in items] == ["t2", "t1"]  # 倒序
            unread_items = await list_notifications(session, user_id=1, unread_only=True)
            assert len(unread_items) == 2

            first = await mark_read(session, user_id=1, notification_id=items[0].id)
            assert first.read_at is not None
            again = await mark_read(session, user_id=1, notification_id=items[0].id)  # 幂等
            assert again.read_at is not None
            assert await unread_count(session, user_id=1) == 1

            marked = await mark_all_read(session, user_id=1)
            assert marked == 1
            assert await unread_count(session, user_id=1) == 0

            try:
                await mark_read(session, user_id=2, notification_id=items[1].id)  # 他人通知
                raise AssertionError("应拒绝")
            except IterdError as exc:
                assert exc.status_code == 404

    asyncio.run(_run())


def test_channel_registry(env: Any) -> None:
    """渠道扩展点：注册即投递、同名覆盖、未注册渠道不投递。"""
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.plugins.notify import (
        Notification,
        notify,
        register_channel,
        unregister_channels_for_test,
    )

    delivered: list[str] = []

    class RecordingChannel:
        name = "recording"

        async def deliver(self, notification: Notification) -> None:
            delivered.append(notification.title)

    class SecondChannel:
        name = "recording"  # 同名覆盖

        async def deliver(self, notification: Notification) -> None:
            delivered.append(f"second:{notification.title}")

    _create_tables()
    factory = get_session_factory(get_engine(get_settings().database_url))

    async def _run() -> None:
        async with factory() as session:
            register_channel(RecordingChannel())  # type: ignore[arg-type]
            register_channel(SecondChannel())  # type: ignore[arg-type]
            await notify(session, user_id=1, ntype="run.completed", title="via-channel")
            assert delivered == ["second:via-channel"]
            unregister_channels_for_test()

    asyncio.run(_run())


def test_run_completed_notification(client: TestClient) -> None:
    """运行完成事件：触发者收到 run.completed 站内信（含结论摘要与跳转链接）。"""
    scenario = _scenario(client)
    _prepare(client, scenario)
    workflow = client.post(
        "/api/v1/workflows",
        json={
            "code": "NT-RULES",
            "name": "纯检查流水线",
            "project_id": scenario["project"]["id"],
            "definition": (
                "name: 纯检查\ndescription: 仅静态检查\n\n"
                "jobs:\n  rules-check:\n    name: 静态规则检查\n    uses: rules/check\n"
                "    with:\n      rule_set: 静态检查集\n"
            ),
        },
    ).json()
    run = _trigger(client, scenario["iteration"]["id"], workflow["id"])
    final = _wait_run(client, run["id"])
    assert final["status"] == "succeeded", final

    items = client.get("/api/v1/notifications").json()
    hits = _by_type(items, "run.completed")
    assert len(hits) == 1
    assert f"#{run['id']}" in hits[0]["title"]
    assert hits[0]["link"] == f"/iterations/{scenario['iteration']['id']}"
    assert hits[0]["resource_type"] == "workflow_run"
    assert "结论 success" in hits[0]["body"]


def test_approval_events_notify_members(client: TestClient) -> None:
    """审批事件链：挂起通知可签成员（范围外不通知）→ 签署后触发者收到进展通知。"""
    scenario = _scenario(client)
    _prepare(client, scenario)
    client.post("/api/v1/users", json={"username": "chief", "password": "chief12345"})
    client.put(
        f"/api/v1/projects/{scenario['project']['id']}/members",
        json={
            "user_id": int(next(u for u in client.get("/api/v1/users").json() if u["username"] == "chief")["id"]),
            "role": "reviewer",
        },
    )
    workflow = _create_workflow(client, scenario)
    run = _trigger(client, scenario["iteration"]["id"], workflow["id"])
    waiting = _wait_run(client, run["id"])
    assert waiting["status"] == "waiting", waiting
    sign_id = next(j["id"] for j in waiting["jobs"] if j["job_key"] == "sign-off")

    # 可签成员 chief 收到审批待办通知
    login_as(client, "chief", "chief12345")
    pending_items = _by_type(client.get("/api/v1/notifications").json(), "approval.pending")
    assert len(pending_items) == 1
    assert pending_items[0]["link"] == "/approvals"
    assert "总师会签" in pending_items[0]["title"]

    # 范围外 designer（非成员）无任何通知
    login_as(client, "designer", "designer123")
    assert _by_type(client.get("/api/v1/notifications").json(), "approval.pending") == []

    # chief 签署 → 运行续跑成功；触发者 admin 收到进展 + 完成通知
    login_as(client, "chief", "chief12345")
    signed = client.post(f"/api/v1/workflow-jobs/{sign_id}/approvals", json={"decision": "approved"})
    assert signed.status_code == 201, signed.text
    final = _wait_run(client, run["id"])
    assert final["status"] == "succeeded", final

    login_as(client, "admin", "admin1234")
    items = client.get("/api/v1/notifications").json()
    recorded = _by_type(items, "approval.recorded")
    completed = _by_type(items, "run.completed")
    assert len(recorded) == 1 and "chief 通过" in recorded[0]["title"]
    assert len(completed) == 1

    # 未读管理与全部已读（admin 为超管，命中审批范围故另有 1 条待办通知）
    assert client.get("/api/v1/notifications/unread-count").json()["count"] == 3
    read_one = client.post(f"/api/v1/notifications/{items[0]['id']}/read")
    assert read_one.status_code == 200 and read_one.json()["read_at"] is not None
    assert client.get("/api/v1/notifications/unread-count").json()["count"] == 2
    marked = client.post("/api/v1/notifications/read-all").json()
    assert marked["marked"] == 2
    assert client.get("/api/v1/notifications/unread-count").json()["count"] == 0
    # unread_only 过滤
    assert client.get("/api/v1/notifications", params={"unread_only": True}).json() == []


def test_notifications_ws_push(client: TestClient) -> None:
    """WebSocket 通知推送：首帧鉴权 → 初始计数帧 → 新通知后计数变化推送。"""
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.plugins.notify import notify

    token = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin1234"}).json()[
        "access_token"
    ]

    with client.websocket_connect("/api/v1/ws/notifications") as ws:
        ws.send_json({"token": token})
        first = ws.receive_json()
        assert first == {"unread_count": 0}

        # 新通知落库 → 轮询循环发现计数变化并推送
        factory = get_session_factory(get_engine(get_settings().database_url))

        async def _create() -> None:
            async with factory() as session:
                me = int(next(u for u in client.get("/api/v1/users").json() if u["username"] == "admin")["id"])
                await notify(session, user_id=me, ntype="run.completed", title="ws-push")
                await session.commit()

        asyncio.run(_create())
        second = ws.receive_json()
        assert second == {"unread_count": 1}
