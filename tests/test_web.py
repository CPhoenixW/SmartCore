from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import crud
from app.db.models import Assignment, LifeEvent
from app.db.session import get_db
from app.main import create_app
from app.secretary.rules import DEFAULT_TZ

DASHBOARD_ROUTES = [
    "/dashboard/today",
    "/dashboard/tomorrow",
    "/dashboard/timetable",
    "/dashboard/assignments",
    "/dashboard/life-events",
    "/dashboard/reminders",
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
