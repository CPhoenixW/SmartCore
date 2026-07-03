from fastapi.testclient import TestClient

from app.main import create_app


def test_work_has_product_state_surface_and_live_dev_state_refresh(app_env) -> None:
    client = TestClient(create_app())

    html = client.get("/work").text
    js = client.get("/static/work/work.js").text
    css = client.get("/static/work/work.css").text

    assert 'data-theme="light"' in html
    assert 'id="currentWorkState"' in html
    assert 'id="workStateLabel"' in html
    assert 'id="workStateSource"' in html
    assert 'id="workStateAge"' in html
    assert 'id="piStateCard"' in html
    assert 'data-state="unknown"' in html

    assert "function pickPrimaryDevState" in js
    assert "function renderPrimaryDevState" in js
    assert "function updateWorkPresence" in js
    assert "currentWorkState" in js
    assert "workStateLabel" in js
    assert "workStateSource" in js
    assert "workStateAge" in js
    assert "loadDevState" in js
    assert "renderPrimaryDevState" in js[js.index("async function loadDevState") :]
    assert "setInterval(refreshDevStatePeriodic, DEV_REFRESH_MS)" in js

    assert ".work-state" in css
    assert ".presence-card" in css
    assert '[data-state="working"]' in css
    assert '[data-state="away"]' in css
    assert '[data-state="offline"]' in css
    assert '[data-state="unknown"]' in css
    assert "border-radius: 8px" in css
    assert "letter-spacing: -" not in css


def test_work_forms_are_polished_and_creation_is_separate_from_board(app_env) -> None:
    client = TestClient(create_app())

    html = client.get("/work").text
    css = client.get("/static/work/work.css").text

    evt_add_start = html.index('data-view="evtAdd"')
    evt_board_start = html.index('data-view="evtBoard"')
    idea_start = html.index('data-view="idea"')
    evt_add_section = html[evt_add_start:evt_board_start]
    evt_board_section = html[evt_board_start:idea_start]

    assert "添加事件" in evt_add_section
    assert "事项看板" in evt_board_section
    assert 'id="lifeEvtForm"' in evt_add_section
    assert 'id="ddlEvtForm"' in evt_add_section
    assert 'id="lifeEvtForm"' not in evt_board_section
    assert 'id="ddlEvtForm"' not in evt_board_section

    assert "普通事项" in evt_add_section
    assert "截止事项" in evt_add_section
    assert "创建 lifeEvt" not in evt_add_section
    assert "创建 ddlEvt" not in evt_add_section
    assert "lifeEvt</strong>" not in evt_add_section
    assert "ddlEvt</strong>" not in evt_add_section

    assert ".field-group" in css
    assert ".input-shell" in css
    assert ".quick-form textarea" in css
    assert "box-shadow" in css
    assert "min-height: 44px" not in css


def test_screen_is_light_landscape_side_panel_with_live_state_classes(app_env) -> None:
    client = TestClient(create_app())

    html = client.get("/screen").text
    js = client.get("/static/screen/screen.js").text
    css = client.get("/static/screen/screen.css").text

    assert 'data-app="smartcore-screen"' in html
    assert 'data-theme="light"' in html
    assert 'id="currentState"' in html
    assert 'id="stateCaption"' in html
    assert 'id="reminderArea"' in html
    assert "横屏" not in html

    assert "--bg: #080b10" not in css
    assert "#0f172a" not in css
    assert "color-scheme: light" in css
    assert "grid-template-columns" in css
    assert "@media (orientation: portrait)" in css
    assert "#currentState.working" in css
    assert "#currentState.away" in css
    assert ".screen-shell" in css

    assert "function renderState" in js
    assert "function applyLayoutMode" in js
    assert "function formatDate" in js
    assert 'id="clockHours"' in html
    assert 'class="digit-sep"' in html
    assert "clockSepEl.classList.toggle" in js
    assert "toLocaleDateString(\"en-US\"" in js
    assert "stateCaption" in js
    assert "className = next" in js
    assert 'data.kind === "devState"' in js
    assert "mode-working" in js
    assert "mode-away" in js
    assert "setWsConnected(false)" in js

    assert 'font-family: "DSEG7"' in css
    assert ".digit-sep.blink-off" in css
    assert ".screen-shell.mode-away" in css
    assert ".screen-shell.mode-away .info-pane" in css
    assert ".screen-shell.mode-away .brand-row" in css


def test_openclaw_agent_skill_can_operate_database_end_to_end(app_env) -> None:
    client = TestClient(create_app())
    headers = {"X-SmartCore-Agent-Token": "agent-secret"}

    blocked = client.get("/agent/tools")
    assert blocked.status_code == 401

    tools = client.get("/agent/tools", headers=headers).json()["tools"]
    assert {tool["name"] for tool in tools} >= {
        "evtQuery",
        "evtCreate",
        "evtUpdate",
        "evtDelete",
        "ideaCapture",
        "ideaToEvt",
    }

    life = client.post(
        "/agent/evtCreate",
        headers=headers,
        json={"evtType": "life", "title": "OpenClaw 创建普通事项", "dueAt": None},
    ).json()
    ddl = client.post(
        "/agent/evtCreate",
        headers=headers,
        json={"evtType": "ddl", "title": "OpenClaw 创建截止事项", "ddlAt": None, "hardDdl": True},
    ).json()

    assert life["ok"] is True
    assert life["stat"] == "done"
    assert ddl["ok"] is True
    assert ddl["data"]["hardDdl"] is True

    evt_id = life["data"]["evtId"]
    queried = client.post("/agent/evtQuery", headers=headers, json={}).json()["data"]["events"]
    assert {evt["evtId"] for evt in queried} >= {evt_id, ddl["data"]["evtId"]}

    updated = client.post(
        "/agent/evtUpdate",
        headers=headers,
        json={"evtId": evt_id, "title": "OpenClaw 已更新", "stat": "done", "prio": "high"},
    ).json()["data"]
    assert updated["title"] == "OpenClaw 已更新"
    assert updated["stat"] == "done"
    assert updated["prio"] == "high"

    deleted = client.post(
        "/agent/evtDelete", headers=headers, json={"evtId": evt_id}
    ).json()["data"]
    assert deleted["stat"] == "cancelled"

    idea = client.post(
        "/agent/ideaCapture",
        headers=headers,
        json={"content": "OpenClaw 捕获灵感", "srcType": "text"},
    ).json()["data"]
    converted = client.post(
        "/agent/ideaToEvt",
        headers=headers,
        json={"ideaId": idea["ideaId"], "title": "灵感转事项", "dueAt": None},
    ).json()["data"]
    assert converted["evtType"] == "life"
    assert converted["title"] == "灵感转事项"

    final_events = client.post("/agent/evtQuery", headers=headers, json={}).json()["data"]["events"]
    assert any(evt["evtId"] == converted["evtId"] for evt in final_events)
    assert "pending" not in str(final_events).lower()
