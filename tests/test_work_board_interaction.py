from fastapi.testclient import TestClient

from app.main import create_app


def test_work_board_cards_are_read_only_and_open_detail_drawer(app_env) -> None:
    client = TestClient(create_app())
    html = client.get("/work").text
    js = client.get("/static/work/work.js").text

    assert 'id="evtDetailDrawer"' in html
    assert 'id="evtDetailForm"' in html
    assert 'data-action="closeEvtDetail"' in html
    assert 'data-action="saveEvtDetail"' in html
    assert 'data-action="completeEvtDetail"' in html
    assert 'data-action="cancelEvtDetail"' in html

    assert 'data-action="openEvtDetail"' in js
    assert "function openEvtDetail" in js
    assert "function closeEvtDetail" in js
    assert "function populateEvtDetail" in js
    assert "function saveEvtDetail" in js
    assert "evtDetailDrawer" in js
    assert "evtDetailForm" in js
    assert "keydown" in js
    assert "Escape" in js

    render_start = js.index("function renderEvtCard")
    render_end = js.index("function applyEvtSearch")
    render_evt_card = js[render_start:render_end]

    assert 'data-action="openEvtDetail"' in render_evt_card
    assert 'tabindex="0"' in render_evt_card
    assert "aria-label" in render_evt_card
    assert 'data-action="fieldEdit"' not in render_evt_card
    assert "inline-title" not in render_evt_card
    assert "inline-desc" not in render_evt_card
    assert "<textarea" not in render_evt_card
    assert "<select" not in render_evt_card
    assert 'data-action="completeEvt"' not in render_evt_card
    assert 'data-action="cancelEvt"' not in render_evt_card


def test_work_board_drawer_has_polished_product_styles(app_env) -> None:
    client = TestClient(create_app())
    css = client.get("/static/work/work.css").text

    assert ".evt-detail-drawer" in css
    assert ".evt-detail-panel" in css
    assert ".evt-detail-backdrop" in css
    assert ".evt-card.active" in css
    assert ".evt-card:focus-visible" in css
    assert ".board-card-title" in css
    assert ".board-card-desc" in css
    assert ".board-card-meta" in css
    assert ".drawer-form" in css
    assert "letter-spacing: -" not in css


def test_work_auto_refresh_preserves_open_event_detail(app_env) -> None:
    client = TestClient(create_app())
    js = client.get("/static/work/work.js").text

    assert "function isEvtDetailOpen" in js
    assert "isEvtDetailOpen()" in js

    refresh_start = js.index("async function refreshActiveView")
    refresh_end = js.index("async function refreshDevStatePeriodic")
    refresh_active_view = js[refresh_start:refresh_end]
    assert "evtBoard" in refresh_active_view
    assert "isEvtDetailOpen()" in refresh_active_view
