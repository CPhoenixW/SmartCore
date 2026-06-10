from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import crud
from app.db.models import (
    Assignment,
    Course,
    CourseSession,
    LifeEvent,
    MessageLog,
    PendingOperationStatus,
    ReminderStatus,
)
from app.db.session import get_db
from app.main import create_app
from app.operations.store import create_pending_operation
from app.secretary.rules import DEFAULT_TZ
from tests.conftest import make_create_event

DASHBOARD_ROUTES = [
    "/dashboard/today",
    "/dashboard/tomorrow",
    "/dashboard/timetable",
    "/dashboard/assignments",
    "/dashboard/life-events",
    "/dashboard/reminders",
    "/dashboard/pending-operations",
    "/dashboard/logs",
]


@pytest.fixture
def web_client(db_session):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_dashboard_routes_are_accessible(web_client):
    for path in DASHBOARD_ROUTES:
        response = web_client.get(path)
        assert response.status_code == 200, path
        assert "SmartCore" in response.text


def test_dashboard_root_redirects_to_today(web_client):
    response = web_client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/today"


def test_dashboard_static_css_loads(web_client):
    response = web_client.get("/dashboard/static/style.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert ":root" in response.text


def test_create_assignment_via_web_form(web_client, db_session):
    response = web_client.post(
        "/dashboard/assignments",
        data={
            "title": "Web Panel Essay",
            "due_at": "2026-05-30T23:59",
            "notes": "from web test",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "Web Panel Essay" in response.text
    assert "已添加作业" in response.text

    assignment = db_session.query(Assignment).filter_by(title="Web Panel Essay").one()
    assert assignment.notes == "from web test"
    assert assignment.due_at is not None


def test_create_life_event_via_web_form(web_client, db_session):
    response = web_client.post(
        "/dashboard/life-events",
        data={"title": "Buy groceries", "notes": "eggs and milk"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "Buy groceries" in response.text
    assert "已添加事项" in response.text

    event = db_session.query(LifeEvent).filter_by(title="Buy groceries").one()
    assert event.notes == "eggs and milk"


def test_view_today_plan_shows_due_assignment(web_client, db_session):
    today = date.today()
    crud.create_assignment(
        db_session,
        title="Due Today Homework",
        due_at=datetime(today.year, today.month, today.day, 18, 0, tzinfo=DEFAULT_TZ),
    )

    response = web_client.get("/dashboard/today")
    assert response.status_code == 200
    assert "今日计划" in response.text
    assert "Due Today Homework" in response.text


def test_today_dashboard_shows_control_center_summary(web_client, db_session):
    reminder = crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 5, 30, 19, 45, tzinfo=DEFAULT_TZ),
        content="提醒：洗澡",
        status=ReminderStatus.SENT,
    )
    reminder.sent_at = datetime(2026, 5, 30, 19, 45, tzinfo=DEFAULT_TZ)
    db_session.commit()
    parsed = make_create_event(
        event_type="schedule",
        title="做程设作业",
        raw_text="添加事项 做程设作业",
        source="feishu",
    )
    create_pending_operation(db_session, parsed)

    response = web_client.get("/dashboard/today")

    assert response.status_code == 200
    assert "中控台" in response.text
    assert "待确认 1" in response.text
    assert "待发送提醒 1" in response.text
    assert "下一条提醒" in response.text
    assert "洗澡" in response.text


def test_reminders_page_shows_notification_log_summary(web_client, db_session):
    first = crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 5, 30, 19, 45, tzinfo=DEFAULT_TZ),
        content="提醒：洗澡",
        status=ReminderStatus.SENT,
    )
    first.sent_at = datetime(2026, 5, 30, 19, 45, tzinfo=DEFAULT_TZ)
    second = crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 5, 30, 20, 45, tzinfo=DEFAULT_TZ),
        status=ReminderStatus.SENT,
        content="提醒：跑步",
    )
    second.sent_at = datetime(2026, 5, 30, 20, 45, tzinfo=DEFAULT_TZ)
    db_session.commit()
    crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 5, 30, 21, 45, tzinfo=DEFAULT_TZ),
        status=ReminderStatus.FAILED,
        content="提醒：复盘",
    )

    response = web_client.get("/dashboard/reminders")

    assert response.status_code == 200
    assert "提醒队列" in response.text
    assert "已发送 2" in response.text
    assert "失败 1" in response.text
    assert "下一条提醒" in response.text
    assert "洗澡" in response.text


def test_logs_page_shows_collapsed_action_debug(web_client, db_session):
    crud.create_message_log(
        db_session,
        source="feishu",
        external_message_id="om_x100b6d18e37e04a0c32d7ed0c2fbcfa",
        raw_content="今晚有什么事",
        parsed_command="query_event",
        reply_status="ok",
        action_input={
            "action": "query_event",
            "raw_text": "今晚有什么事",
            "payload": {"filter": {"event_type": "all"}},
        },
        db_result={"ok": True, "status": "applied", "data": {"count": 0}},
    )

    response = web_client.get("/dashboard/logs")

    assert response.status_code == 200
    assert "row-toggle" in response.text
    assert "debug-row" in response.text
    assert "debug-grid" in response.text
    assert "copy-id" in response.text
    assert "om_x100b6d...2fbcfa" in response.text
    assert "data-copy-value=\"om_x100b6d18e37e04a0c32d7ed0c2fbcfa\"" in response.text
    assert "模型输入" in response.text
    assert "数据库执行结果" in response.text
    assert "query_event" in response.text
    assert "今晚有什么事" in response.text
    assert "\\u4eca\\u665a" not in response.text


def test_timetable_import_via_web_form(web_client, db_session):
    csv_content = (
        "course_name,teacher,default_location,weekday,start_time,end_time,"
        "week_rule,week_range,location_override\n"
        "Physics,Dr. Lee,Room B201,2,10:00,11:40,every,,\n"
    )
    response = web_client.post(
        "/dashboard/timetable",
        data={"csv_content": csv_content},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "导入完成" in response.text

    course = db_session.query(Course).filter_by(name="Physics").one()
    assert course.default_location == "Room B201"
    assert len(course.sessions) == 1


def test_timetable_import_replaces_previous_timetable(web_client, db_session):
    old_course = crud.create_course(db_session, name="Old Course")
    crud.create_course_session(
        db_session,
        course_id=old_course.id,
        weekday=1,
        start_time="08:00",
        end_time="09:40",
    )
    csv_content = (
        "course_name,teacher,default_location,weekday,start_time,end_time,"
        "week_rule,week_range,location_override\n"
        "New Course,Dr. New,Room N,2,19:00,20:30,every,,\n"
    )

    response = web_client.post(
        "/dashboard/timetable",
        data={"csv_content": csv_content},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "导入完成" in response.text
    assert db_session.query(CourseSession).count() == 1
    assert db_session.query(Course).filter_by(name="Old Course").count() == 0
    new_course = db_session.query(Course).filter_by(name="New Course").one()
    assert new_course.sessions[0].weekday == 2


def test_assignment_page_exposes_and_handles_delete_button(web_client, db_session):
    assignment = crud.create_assignment(db_session, title="Delete me")

    page = web_client.get("/dashboard/assignments")
    assert page.status_code == 200
    assert f"/dashboard/assignments/{assignment.id}/delete" in page.text
    assert "删除" in page.text

    response = web_client.post(
        f"/dashboard/assignments/{assignment.id}/delete",
        follow_redirects=False,
    )

    db_session.refresh(assignment)
    assert response.status_code == 303
    assert assignment.status == "cancelled"


def test_life_event_page_exposes_and_handles_delete_button(web_client, db_session):
    event = crud.create_life_event(db_session, title="Delete event")

    page = web_client.get("/dashboard/life-events")
    assert page.status_code == 200
    assert f"/dashboard/life-events/{event.id}/delete" in page.text
    assert "删除" in page.text

    response = web_client.post(
        f"/dashboard/life-events/{event.id}/delete",
        follow_redirects=False,
    )

    db_session.refresh(event)
    assert response.status_code == 303
    assert event.status == "cancelled"


def test_pending_operations_page_can_confirm_operation(web_client, db_session):
    parsed = make_create_event(
        event_type="schedule",
        title="做程设作业",
        raw_text="添加事项 做程设作业",
        source="feishu",
    )
    pending = create_pending_operation(db_session, parsed)

    response = web_client.get("/dashboard/pending-operations")
    assert response.status_code == 200
    assert "做程设作业" in response.text

    confirm = web_client.post(
        f"/dashboard/pending-operations/{pending.id}/confirm",
        follow_redirects=False,
    )

    db_session.refresh(pending)
    event = db_session.query(LifeEvent).filter_by(title="做程设作业").one()
    assert confirm.status_code == 303
    assert pending.status == PendingOperationStatus.APPLIED.value
    assert pending.result_resource_id == event.id


def test_pending_operations_page_can_update_raw_command(
    web_client, db_session, monkeypatch
) -> None:
    parsed = make_create_event(
        event_type="schedule",
        title="旧命令",
        raw_text="添加事项 旧命令",
        source="feishu",
    )
    pending = create_pending_operation(db_session, parsed)

    class FakeLLMParser:
        def parse(self, text: str, *, source: str, now=None):
            assert text == "添加事项 新命令"
            return make_create_event(
                event_type="schedule",
                title="新命令",
                raw_text=text,
                source=source,
            )

    from app.operations.parser import OperationParser
    from app.web import routes as web_routes

    monkeypatch.setattr(
        web_routes,
        "build_operation_parser",
        lambda _settings: OperationParser(FakeLLMParser()),
    )

    response = web_client.post(
        f"/dashboard/pending-operations/{pending.id}/update",
        data={"raw_text": "添加事项 新命令"},
        follow_redirects=False,
    )

    db_session.refresh(pending)
    assert response.status_code == 303
    assert pending.raw_text == "添加事项 新命令"
    assert pending.operation_payload["payload"]["event"]["title"] == "新命令"


def test_pending_operations_page_shows_recent_operation_audit(web_client, db_session):
    parsed = make_create_event(
        event_type="schedule",
        title="失败操作",
        raw_text="添加事项 失败操作",
        source="feishu",
    )
    pending = create_pending_operation(db_session, parsed)
    pending.status = PendingOperationStatus.FAILED.value
    pending.error_message = "simulated failure"
    db_session.commit()

    response = web_client.get("/dashboard/pending-operations")

    assert response.status_code == 200
    assert "操作审计" in response.text
    assert "失败操作" in response.text
    assert "failed" in response.text
    assert "simulated failure" in response.text


def test_logs_page_shows_message_logs_and_operation_audit(web_client, db_session):
    db_session.add(
        MessageLog(
            source="feishu",
            external_message_id="om_help",
            raw_content="晚上十点提醒我写作业",
            parsed_command="help",
            reply_status="help",
        )
    )
    parsed = make_create_event(
        event_type="schedule",
        title="失败操作",
        raw_text="添加事项 失败操作",
        source="feishu",
    )
    pending = create_pending_operation(db_session, parsed)
    pending.status = PendingOperationStatus.FAILED.value
    pending.error_message = "schema mismatch"
    db_session.commit()

    response = web_client.get("/dashboard/logs")

    assert response.status_code == 200
    assert "运行日志" in response.text
    assert "飞书消息日志" in response.text
    assert "晚上十点提醒我写作业" in response.text
    assert "om_help" in response.text
    assert "help" in response.text
    assert "操作审计" in response.text
    assert "失败操作" in response.text
    assert "schema mismatch" in response.text
