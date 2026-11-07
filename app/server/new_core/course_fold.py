"""Turn course templates into ordinary plans.

Occurrence plans and their reminders stay. Course name, teacher, location and
week are copied into the plan description, then the template and link rows go
away. Running this again is a no-op.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.new_core.course_semester import sync_course_plans
from app.server.new_core.models import CourseEvt, CoursePlan, EvtBase, nowIso


def _course_line(course: CourseEvt, link: CoursePlan) -> str:
    parts = [f"课程：{course.courseName}"]
    if course.teacher:
        parts.append(f"教师：{course.teacher}")
    if course.location:
        parts.append(f"地点：{course.location}")
    parts.append(f"第{link.sequenceNo}周 {link.occurrenceDate}")
    return "，".join(parts)


def fold_courses_into_plans(db: Session) -> dict[str, int]:
    course_ids = [str(value) for value in db.scalars(select(CourseEvt.evtId)).all()]
    folded = 0
    plans = 0
    for course_id in course_ids:
        course = db.get(CourseEvt, course_id)
        base = db.get(EvtBase, course_id)
        if course is None:
            continue
        links = list(db.scalars(select(CoursePlan).where(CoursePlan.courseEvtId == course_id)).all())
        if not links:
            sync_course_plans(db, course_id)
            links = list(db.scalars(select(CoursePlan).where(CoursePlan.courseEvtId == course_id)).all())
        for link in links:
            plan_base = db.get(EvtBase, link.planEvtId)
            if plan_base is None:
                continue
            marker = f"课程：{course.courseName}"
            current = plan_base.desc or ""
            if marker not in current:
                line = _course_line(course, link)
                plan_base.desc = f"{current}\n{line}".strip() if current else line
                plan_base.updatedAt = nowIso()
            plans += 1
        for link in links:
            db.delete(link)
        db.flush()
        db.delete(course)
        if base is not None and base.evtType == "course":
            db.delete(base)
        folded += 1
    if folded:
        db.commit()
    return {"courses": folded, "plans": plans}


def fold_course_payload(db: Session, result: dict[str, Any]) -> dict[str, Any]:
    summary = fold_courses_into_plans(db)
    payload = dict(result)
    payload["foldedIntoPlans"] = summary["courses"] > 0
    payload["keptPlans"] = summary["plans"]
    return payload
