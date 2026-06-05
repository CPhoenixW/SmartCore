from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import crud
from app.db.models import (
    Assignment,
    LifeEvent,
    PendingOperationStatus,
    ReminderStatus,
)
from app.db.session import get_db
from app.main import create_app
from app.operations.parser import RuleBasedOperationParser
from app.operations.store import create_pending_operation
from app.secretary.rules import DEFAULT_TZ

DASHBOARD_ROUTES = [
    "/dashboard/today",
    "/dashboard/tomorrow",
    "/dashboard/timetable",
    "/dashboard/assignments",
    "/dashboard/life-events",
    "/dashboard/reminders",
    "/dashboard/pending-operations",
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
    crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 5, 30, 19, 45, tzinfo=DEFAULT_TZ),
        content="提醒：洗澡",
    )
    parsed = RuleBasedOperationParser(tz=DEFAULT_TZ).parse(
        "添加事项 做程设作业",
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


def test_reminders_page_shows_queue_summary(web_client, db_session):
    crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 5, 30, 19, 45, tzinfo=DEFAULT_TZ),
        content="提醒：洗澡",
    )
    crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 5, 30, 20, 45, tzinfo=DEFAULT_TZ),
        status=ReminderStatus.SENT,
        content="提醒：跑步",
    )
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
    assert "待发送 1" in response.text
    assert "已发送 1" in response.text
    assert "失败 1" in response.text
    assert "下一条提醒" in response.text
    assert "洗澡" in response.text


def test_reminders_page_can_cancel_pending_reminder(web_client, db_session):
    reminder = crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 5, 30, 19, 45, tzinfo=DEFAULT_TZ),
        content="提醒：洗澡",
    )

    response = web_client.post(
        f"/dashboard/reminders/{reminder.id}/cancel",
        follow_redirects=False,
    )

    db_session.refresh(reminder)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/reminders"
    assert reminder.status == ReminderStatus.CANCELLED.value


def test_reminders_page_can_update_pending_reminder_time(web_client, db_session):
    reminder = crud.create_reminder(
        db_session,
        reminder_type="life_event_pre_event",
        target_type="life_event",
        scheduled_at=datetime(2026, 5, 30, 19, 45, tzinfo=DEFAULT_TZ),
        content="提醒：洗澡",
    )

    response = web_client.post(
        f"/dashboard/reminders/{reminder.id}/update",
        data={"scheduled_at": "2026-05-30T20:30"},
        follow_redirects=False,
    )

    db_session.refresh(reminder)
    scheduled_at = reminder.scheduled_at
    if scheduled_at is not None and scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=DEFAULT_TZ)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/reminders"
    assert scheduled_at == datetime(2026, 5, 30, 20, 30, tzinfo=DEFAULT_TZ)


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

    from app.db.models import Course

    course = db_session.query(Course).filter_by(name="Physics").one()
    assert course.default_location == "Room B201"
    assert len(course.sessions) == 1


def test_pending_operations_page_can_confirm_operation(web_client, db_session):
    parsed = RuleBasedOperationParser(tz=DEFAULT_TZ).parse(
        "添加事项 做程设作业",
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


def test_pending_operations_page_can_update_raw_command(web_client, db_session):
    parsed = RuleBasedOperationParser(tz=DEFAULT_TZ).parse(
        "添加事项 旧命令",
        source="feishu",
    )
    pending = create_pending_operation(db_session, parsed)

    response = web_client.post(
        f"/dashboard/pending-operations/{pending.id}/update",
        data={"raw_text": "添加事项 新命令"},
        follow_redirects=False,
    )

    db_session.refresh(pending)
    assert response.status_code == 303
    assert pending.raw_text == "添加事项 新命令"
    assert pending.operation_payload["fields"]["title"] == "新命令"
