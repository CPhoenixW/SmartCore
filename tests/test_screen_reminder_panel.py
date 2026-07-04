from fastapi.testclient import TestClient

from app.main import create_app


def test_work_nav_uses_quiet_text_tabs(app_env) -> None:
    client = TestClient(create_app())
    css = client.get("/static/work/work.css").text

    nav_start = css.index(".nav-tab {")
    nav_end = css.index(".nav-tab:hover")
    nav_block = css[nav_start:nav_end]
    assert "border: none" in nav_block
    assert "background: transparent" in nav_block
    assert "box-shadow" not in nav_block
    assert "border: 1px" not in nav_block
    assert ".nav-tab.active::after" in css


def test_screen_has_today_panel_and_dedicated_audible_reminder_page(app_env) -> None:
    client = TestClient(create_app())
    html = client.get("/screen").text
    js = client.get("/static/screen/screen.js").text
    css = client.get("/static/screen/screen.css").text

    assert 'id="latestReminderList"' in html
    assert 'id="todayEvtList"' in html
    assert 'id="expiredReminderList"' in html
    assert 'id="reminderPage"' in html
    assert 'id="reminderDone"' in html
    assert 'id="reminderSnooze"' in html

    assert "function loadTodayEvents" in js
    assert "function renderTodayEvents" in js
    assert "function showReminderPage" in js
    assert "function expireActiveReminder" in js
    assert "function submitReminderAction" in js
    assert "function playReminderSound" in js
    assert "AudioContext" in js
    assert "/api/evt" in js
    assert "/api/reminder/action" in js
    assert "today-primary" in js
    assert "today-compact" in js
    assert "setTimeout(expireActiveReminder, 60000)" in js

    assert ".reminder-page" in css
    assert ".reminder-page.show" in css
    assert ".reminder-actions" in css
    assert ".reminder-zone.latest" in css
    assert ".reminder-zone.day-plan" in css
    assert ".reminder-zone.expired" in css
    assert ".expired-reminder" in css
    assert ".today-primary" in css
    assert ".today-compact" in css


def test_screen_manager_reports_delivery_result() -> None:
    from app.screen.manager import ScreenManager

    manager = ScreenManager()
    assert manager.broadcastFromThread({"kind": "reminder"}) is False
