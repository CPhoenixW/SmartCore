import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.server.db.session import Base
from app.server.new_core.course_fold import fold_courses_into_plans
from app.server.new_core.course_semester import create_course_event
from app.server.new_core.models import CourseEvt, CoursePlan, EvtBase, PlanEvt, RemindEvt

pytestmark = pytest.mark.unit


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_fold_keeps_occurrence_plans_and_drops_the_template() -> None:
    db = _session()
    try:
        create_course_event(
            db,
            courseName="Robotics",
            teacher="Teacher Wang",
            location="A101",
            semesterStart="2026-09-07",
            weekDay=2,
            stTime="08:00",
            endTime="09:40",
            startWeek=1,
            endWeek=3,
        )
        summary = fold_courses_into_plans(db)

        assert summary == {"courses": 1, "plans": 3}
        assert db.scalar(select(func.count()).select_from(CourseEvt)) == 0
        assert db.scalar(select(func.count()).select_from(CoursePlan)) == 0
        assert db.scalar(select(func.count()).select_from(PlanEvt)) == 3
        assert db.scalar(select(func.count()).select_from(RemindEvt)) == 6
        descriptions = [row.desc or "" for row in db.scalars(select(EvtBase).where(EvtBase.evtType == "plan")).all()]
        assert descriptions
        assert all("课程：Robotics" in item for item in descriptions)
        assert all("教师：Teacher Wang" in item for item in descriptions)
        assert all("地点：A101" in item for item in descriptions)
        assert fold_courses_into_plans(db) == {"courses": 0, "plans": 0}
        assert db.scalar(select(func.count()).select_from(PlanEvt)) == 3
    finally:
        db.close()
