from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.config import get_settings
from app.server.new_core.event_relations import (
    _DEFAULT_USER_ID,
    _course_dict,
    _course_plan_spec,
    _delete_plan_tree,
    _ensure_user,
    _normalize_weekday,
    _parse_clock,
    _parse_date,
    _record_action,
    create_plan_event,
    sync_plan_reminders,
)
from app.server.new_core.models import CourseEvt, CoursePlan, EvtBase, PlanEvt, newId, nowIso

_DEFAULT_END_WEEK = 16


def _resolve_semester_start(
    *,
    semester_start: str | date | None = None,
    st_date: str | date | None = None,
) -> date:
    raw = semester_start or st_date or get_settings().semester_start
    if raw is None:
        raise ValueError("semesterStart required")
    if isinstance(raw, date):
        return raw
    return _parse_date(str(raw))


def _resolve_week_range(
    *,
    semester_start: date,
    start_week: int | None,
    end_week: int | None,
    legacy_end_date: str | date | None = None,
) -> tuple[int, int]:
    start = int(start_week or 1)
    if start < 1:
        raise ValueError("startWeek must be greater than 0")

    if end_week is not None:
        end = int(end_week)
    elif legacy_end_date is not None:
        legacy_end = legacy_end_date if isinstance(legacy_end_date, date) else _parse_date(str(legacy_end_date))
        anchor_monday = semester_start - timedelta(days=semester_start.isoweekday() - 1)
        end = ((legacy_end - anchor_monday).days // 7) + 1
    else:
        end = _DEFAULT_END_WEEK

    if end < start:
        raise ValueError("endWeek must not be earlier than startWeek")
    return start, end


def expand_course_dates_from_semester(
    *,
    semester_start: str | date,
    week_day: Any,
    start_week: int = 1,
    end_week: int = _DEFAULT_END_WEEK,
    week_mode: str = "all",
) -> list[date]:
    semester = semester_start if isinstance(semester_start, date) else _parse_date(str(semester_start))
    weekday = _normalize_weekday(week_day)
    mode = str(week_mode or "all").lower()
    if mode not in {"all", "odd", "even"}:
        raise ValueError("weekMode must be all, odd, or even")
    if start_week < 1:
        raise ValueError("startWeek must be greater than 0")
    if end_week < start_week:
        raise ValueError("endWeek must not be earlier than startWeek")

    anchor_monday = semester - timedelta(days=semester.isoweekday() - 1)
    result: list[date] = []
    for week_number in range(start_week, end_week + 1):
        if mode == "odd" and week_number % 2 == 0:
            continue
        if mode == "even" and week_number % 2 == 1:
            continue
        occurrence = anchor_monday + timedelta(
            days=(week_number - 1) * 7 + (weekday - 1)
        )
        if occurrence < semester:
            continue
        result.append(occurrence)
    return result


def _course_result(db: Session, base: EvtBase, course: CourseEvt) -> dict[str, Any]:
    result = _course_dict(db, base, course)
    result["semesterStart"] = course.stDate
    result["computedEndDate"] = course.endDate
    return result


def sync_course_plans(db: Session, course_evt_id: str) -> list[dict[str, Any]]:
    base = db.get(EvtBase, course_evt_id)
    course = db.get(CourseEvt, course_evt_id)
    if base is None or course is None:
        raise ValueError(f"course not found: {course_evt_id}")

    semester_start = _parse_date(course.stDate)
    start_week, end_week = _resolve_week_range(
        semester_start=semester_start,
        start_week=course.startWeek,
        end_week=course.endWeek,
        legacy_end_date=course.endDate,
    )
    desired_dates = expand_course_dates_from_semester(
        semester_start=semester_start,
        week_day=course.weekDay,
        start_week=start_week,
        end_week=end_week,
        week_mode=course.weekMode,
    )
    course.startWeek = start_week
    course.endWeek = end_week
    course.endDate = (desired_dates[-1] if desired_dates else semester_start).isoformat()

    existing_links = db.scalars(
        select(CoursePlan).where(CoursePlan.courseEvtId == course_evt_id)
    ).all()
    existing = {link.occurrenceDate: link for link in existing_links}
    desired_keys = {item.isoformat() for item in desired_dates}

    for sequence, occurrence in enumerate(desired_dates, start=1):
        spec = _course_plan_spec(course, base, occurrence, sequence)
        link = existing.get(spec["occurrenceDate"])
        if link is None:
            plan_result = create_plan_event(
                db,
                title=spec["title"],
                stTime=spec["stTime"],
                durationMin=spec["durationMin"],
                desc=spec["desc"],
                prio=base.prio,
                src="course-generator",
                userId=base.userId,
                commit=False,
            )
            db.add(
                CoursePlan(
                    courseEvtId=course_evt_id,
                    planEvtId=plan_result["evtId"],
                    occurrenceDate=spec["occurrenceDate"],
                    sequenceNo=sequence,
                )
            )
            continue

        link.sequenceNo = sequence
        plan_base = db.get(EvtBase, link.planEvtId)
        plan = db.get(PlanEvt, link.planEvtId)
        if plan_base is None or plan is None:
            continue
        changed = plan.stTime != spec["stTime"] or plan.durationMin != spec["durationMin"]
        plan_base.title = spec["title"]
        plan_base.desc = spec["desc"]
        plan_base.prio = base.prio
        if base.stat != "todo" and plan_base.stat == "todo":
            plan_base.stat = "cancelled"
        plan_base.updatedAt = nowIso()
        plan.stTime = spec["stTime"]
        plan.durationMin = spec["durationMin"]
        sync_plan_reminders(db, plan_base.evtId, reset_fired=changed)

    for occurrence_date, link in existing.items():
        if occurrence_date not in desired_keys:
            _delete_plan_tree(db, link.planEvtId)

    db.flush()
    return _course_dict(db, base, course)["plans"]


def create_course_event(
    db: Session,
    *,
    courseName: str,
    stTime: str,
    endTime: str,
    weekDay: Any,
    semesterStart: str | date | None = None,
    stDate: str | date | None = None,
    endDate: str | date | None = None,
    title: str | None = None,
    teacher: str | None = None,
    location: str | None = None,
    startWeek: int | None = 1,
    endWeek: int | None = _DEFAULT_END_WEEK,
    weekMode: str = "all",
    desc: str | None = None,
    prio: str = "mid",
    src: str = "api",
    userId: str = _DEFAULT_USER_ID,
) -> dict[str, Any]:
    _ensure_user(db, userId)
    clean_name = str(courseName).strip()
    if not clean_name:
        raise ValueError("courseName required")
    weekday = _normalize_weekday(weekDay)
    _parse_clock(stTime)
    _parse_clock(endTime)
    semester = _resolve_semester_start(semester_start=semesterStart, st_date=stDate)
    first_week, last_week = _resolve_week_range(
        semester_start=semester,
        start_week=startWeek,
        end_week=endWeek,
        legacy_end_date=endDate,
    )
    dates = expand_course_dates_from_semester(
        semester_start=semester,
        week_day=weekday,
        start_week=first_week,
        end_week=last_week,
        week_mode=weekMode,
    )

    now = nowIso()
    base = EvtBase(
        evtId=newId(),
        userId=userId,
        title=(title or clean_name).strip(),
        desc=desc,
        evtType="course",
        prio=prio,
        stat="todo",
        createdAt=now,
        updatedAt=now,
    )
    db.add(base)
    db.flush()
    course = CourseEvt(
        evtId=base.evtId,
        courseName=clean_name,
        teacher=teacher,
        location=location,
        stTime=str(stTime)[:8],
        endTime=str(endTime)[:8],
        stDate=semester.isoformat(),
        endDate=(dates[-1] if dates else semester).isoformat(),
        weekDay=weekday,
        startWeek=first_week,
        endWeek=last_week,
        weekMode=str(weekMode or "all").lower(),
    )
    db.add(course)
    db.flush()
    sync_course_plans(db, base.evtId)
    _record_action(
        db,
        user_id=userId,
        src=src,
        action="create",
        target_kind="courseEvt",
        target_id=base.evtId,
    )
    db.commit()
    return _course_result(db, base, course)


def update_course_event(
    db: Session,
    course_evt_id: str,
    *,
    src: str = "api",
    **fields: Any,
) -> dict[str, Any]:
    base = db.get(EvtBase, course_evt_id)
    course = db.get(CourseEvt, course_evt_id)
    if base is None or course is None:
        raise ValueError(f"course not found: {course_evt_id}")

    for key in ("title", "desc", "prio", "stat"):
        if key in fields and fields[key] is not None:
            setattr(base, key, fields[key])
    if fields.get("courseName") is not None:
        clean_name = str(fields["courseName"]).strip()
        if not clean_name:
            raise ValueError("courseName required")
        course.courseName = clean_name
        if "title" not in fields:
            base.title = clean_name
    for key in ("teacher", "location"):
        if key in fields:
            setattr(course, key, fields[key] or None)
    if fields.get("stTime") is not None:
        _parse_clock(str(fields["stTime"]))
        course.stTime = str(fields["stTime"])[:8]
    if fields.get("endTime") is not None:
        _parse_clock(str(fields["endTime"]))
        course.endTime = str(fields["endTime"])[:8]
    if fields.get("weekDay") is not None:
        course.weekDay = _normalize_weekday(fields["weekDay"])
    if fields.get("weekMode") is not None:
        course.weekMode = str(fields["weekMode"]).lower()

    semester_raw = fields.get("semesterStart", fields.get("stDate", course.stDate))
    semester = _resolve_semester_start(semester_start=semester_raw)
    first_week, last_week = _resolve_week_range(
        semester_start=semester,
        start_week=fields.get("startWeek", course.startWeek),
        end_week=fields.get("endWeek", course.endWeek),
        legacy_end_date=fields.get("endDate"),
    )
    course.stDate = semester.isoformat()
    course.startWeek = first_week
    course.endWeek = last_week
    base.updatedAt = nowIso()
    sync_course_plans(db, course_evt_id)
    _record_action(
        db,
        user_id=base.userId,
        src=src,
        action="update",
        target_kind="courseEvt",
        target_id=course_evt_id,
    )
    db.commit()
    return _course_result(db, base, course)


def get_course_event(db: Session, course_evt_id: str) -> dict[str, Any]:
    base = db.get(EvtBase, course_evt_id)
    course = db.get(CourseEvt, course_evt_id)
    if base is None or course is None:
        raise ValueError(f"course not found: {course_evt_id}")
    return _course_result(db, base, course)


def list_course_events(db: Session, *, user_id: str = _DEFAULT_USER_ID) -> list[dict[str, Any]]:
    rows = db.execute(
        select(EvtBase, CourseEvt)
        .join(CourseEvt, CourseEvt.evtId == EvtBase.evtId)
        .where(EvtBase.userId == user_id)
        .order_by(CourseEvt.weekDay.asc(), CourseEvt.stTime.asc())
    ).all()
    return [_course_result(db, base, course) for base, course in rows]
