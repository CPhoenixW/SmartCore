from fastapi.testclient import TestClient

from app.main import create_app


def test_healthz(app_env) -> None:
    client = TestClient(create_app())

    assert client.get("/healthz").json() == {"status": "ok"}


def test_life_ddl_idea_and_undo_api(app_env) -> None:
    client = TestClient(create_app())

    life_resp = client.post(
        "/api/lifeEvt",
        json={"title": "写重构计划", "dueAt": "2026-07-03T20:00:00+08:00"},
    )
    ddl_resp = client.post(
        "/api/ddlEvt",
        json={"title": "交作业", "ddlAt": "2026-07-04T23:00:00+08:00", "hardDdl": True},
    )
    idea_resp = client.post("/api/idea", json={"content": "做一个副屏模式", "srcType": "text"})

    assert life_resp.status_code == 200
    assert ddl_resp.status_code == 200
    assert idea_resp.status_code == 200
    assert client.get("/api/evt").json()["data"][0]["evtId"] == life_resp.json()["data"]["evtId"]

    undo_token = client.get("/api/actLog").json()["data"][-1]["undoToken"]
    undo_resp = client.post(f"/api/undo/{undo_token}")
    assert undo_resp.status_code == 200
    assert undo_resp.json()["ok"] is True


def test_full_internal_api_surface_uses_new_arch_names(app_env) -> None:
    client = TestClient(create_app())

    life = client.post(
        "/api/lifeEvt",
        json={"title": "整理桌面", "dueAt": "2026-07-03T21:00:00+08:00"},
    ).json()["data"]
    ddl = client.post(
        "/api/ddlEvt",
        json={"title": "提交实验报告", "ddlAt": "2026-07-05T23:00:00+08:00"},
    ).json()["data"]
    tpl = client.post(
        "/api/courseTpl",
        json={
            "courseName": "数据库",
            "teacher": "王老师",
            "room": "A101",
            "weekday": 1,
            "startTime": "08:00",
            "endTime": "09:40",
            "startWeek": 1,
            "endWeek": 16,
            "weekMode": "all",
            "semester": "2026-spring",
        },
    ).json()["data"]
    course = client.post(
        "/api/courseInst",
        json={
            "title": "数据库",
            "tplId": tpl["tplId"],
            "classDate": "2026-07-06",
            "attendStat": "unknown",
        },
    ).json()["data"]
    idea = client.post("/api/idea", json={"content": "把飞书回复做短一点"}).json()["data"]
    converted = client.post(
        f"/api/idea/{idea['ideaId']}/toEvt",
        json={"title": "优化飞书短回复", "dueAt": None},
    ).json()["data"]

    assert client.get("/api/lifeEvt").json()["data"][0]["evtId"] == life["evtId"]
    assert client.get("/api/ddlEvt").json()["data"][0]["evtId"] == ddl["evtId"]
    assert client.get("/api/courseTpl").json()["data"][0]["tplId"] == tpl["tplId"]
    assert client.get("/api/courseInst").json()["data"][0]["evtId"] == course["evtId"]
    assert converted["evtType"] == "life"

    patched = client.patch(
        f"/api/evt/{life['evtId']}",
        json={"title": "整理工作区", "prio": "high"},
    ).json()["data"]
    cancelled = client.delete(f"/api/evt/{ddl['evtId']}").json()["data"]

    assert patched["title"] == "整理工作区"
    assert patched["prio"] == "high"
    assert cancelled["stat"] == "cancelled"
    assert client.get("/api/notifyLog").status_code == 200


def test_device_state_api_requires_token_and_records_state(app_env) -> None:
    client = TestClient(create_app())

    blocked = client.post("/dev/state", json={"devId": "pi", "state": "working"})
    assert blocked.status_code == 401

    accepted = client.post(
        "/dev/state",
        headers={"X-SmartCore-Device-Token": "device-secret"},
        json={"devId": "pi", "state": "working", "confidence": 0.91, "meta": {"src": "yolo"}},
    )
    assert accepted.status_code == 200
    state = client.get("/api/devState").json()["data"][0]
    assert state["stateId"] is not None
    assert state["state"] == "working"


def test_agent_tools_and_direct_write_flow(app_env) -> None:
    client = TestClient(create_app())
    headers = {"X-SmartCore-Agent-Token": "agent-secret"}

    tools = client.get("/agent/tools", headers=headers).json()["tools"]
    assert [tool["name"] for tool in tools] == [
        "evtQuery",
        "evtCreate",
        "evtUpdate",
        "evtDelete",
        "ideaCapture",
        "ideaToEvt",
        "sendText",
        "sendCard",
        "screenPush",
    ]

    create_resp = client.post(
        "/agent/evtCreate",
        headers=headers,
        json={"evtType": "life", "title": "直接执行事项", "dueAt": None},
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["stat"] == "done"
    assert "pending" not in str(create_resp.json()).lower()


def test_work_and_screen_pages_are_accessible_over_tailnet(app_env) -> None:
    client = TestClient(create_app())

    assert client.get("/work").status_code == 200
    assert client.get("/screen").status_code == 200


def test_work_dashboard_has_operational_controls(app_env) -> None:
    client = TestClient(create_app())
    html = client.get("/work").text

    assert 'id="lifeEvtForm"' in html
    assert 'id="ddlEvtForm"' in html
    assert 'id="ideaForm"' in html
    assert 'id="evtBoard"' in html
    assert 'id="evtListTodo"' in html
    assert 'id="evtListDone"' in html
    assert 'id="evtListCancelled"' in html
    assert 'data-action="completeEvt"' in html
    assert 'data-action="cancelEvt"' in html
    assert 'data-action="setPrio"' in html
    assert 'id="devStatePanel"' in html
    assert 'id="notifyLogPanel"' in html
    assert 'id="msgLogPanel"' in html
    assert 'id="actLogPanel"' in html
    assert 'data-action="refreshEvt"' in html
    assert "/api/lifeEvt" in html
    assert "/api/ddlEvt" in html
    assert "/api/idea" in html
    assert "/api/evt" in html
    assert 'href="/api/evt"' not in html
    assert "pending" not in html.lower()
    assert "/dashboard" not in html


def test_screen_page_has_websocket_ui_markers(app_env) -> None:
    client = TestClient(create_app())
    html = client.get("/screen").text

    assert "/screen/ws" in html
    assert "WebSocket" in html
    assert 'id="clock"' in html
    assert 'data-ws-ui="clock"' in html
    assert 'id="currentState"' in html
    assert 'data-ws-ui="state"' in html
    assert 'id="reminderArea"' in html
    assert 'data-ws-ui="reminder"' in html
    assert 'id="wsStatus"' in html
    assert 'data-ws-ui="status"' in html
    assert "handleWsMessage" in html
