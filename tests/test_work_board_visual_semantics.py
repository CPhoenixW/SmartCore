from fastapi.testclient import TestClient

from app.main import create_app


def test_work_board_uses_semantic_time_and_priority_palette(app_env) -> None:
    client = TestClient(create_app())
    js = client.get("/static/work/work.js").text
    css = client.get("/static/work/work.css").text

    assert "function getEvtTime" in js
    assert "function fmtBoardTime" in js
    assert "明天" in js
    assert "今天" in js
    assert "已逾期" in js
    assert "board-card-time overdue" in js
    assert "月${dt.getDate()}日" in js

    assert ".tag.prio-high" in css
    assert "#fef2f2" in css
    assert "#dc2626" in css
    assert ".tag.prio-mid" in css
    assert "#fffbeb" in css
    assert "#ca8a04" in css
    assert ".tag.prio-low" in css
    assert "#eff6ff" in css
    assert "#2563eb" in css
    assert ".board-card-time.overdue" in css


def test_work_board_card_actions_follow_column_state(app_env) -> None:
    client = TestClient(create_app())
    js = client.get("/static/work/work.js").text

    assert "function renderEvtActions" in js
    assert "completeEvt" in js
    assert "cancelEvt" in js
    assert "reopenEvt" in js
    assert "evt.stat === \"todo\"" in js
    assert "evt.stat === \"done\" || evt.stat === \"cancelled\"" in js
    assert "ev.stopPropagation()" in js

    render_start = js.index("function renderEvtCard")
    render_end = js.index("function applyEvtSearch")
    render_evt_card = js[render_start:render_end]

    assert "renderEvtActions(evt)" in render_evt_card
    assert 'data-action="fieldEdit"' not in render_evt_card
    assert "<textarea" not in render_evt_card
    assert "<select" not in render_evt_card
    assert "stat-" not in render_evt_card


def test_work_board_has_landscape_phone_density(app_env) -> None:
    client = TestClient(create_app())
    css = client.get("/static/work/work.css").text

    assert "orientation: landscape" in css
    assert "max-height: 520px" in css
    assert ".evt-columns" in css
    assert ".evt-col-list" in css
    assert "letter-spacing: -" not in css
