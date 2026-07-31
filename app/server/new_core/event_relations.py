from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.config import get_settings
from app.server.new_core.models import (
    ActLog,
    CourseEvt,
    CoursePlan,
    DdlEvt,
    DdlPlan,
    EvtBase,
    PlanEvt,
    RemindEvt,
    newId,
    nowIso,
)

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")
_DEFAULT_USER_ID = "default"
_REMINDER_OFFSET_MIN = 10
_REMINDER_KINDS = ("plan_start_10m", "plan_end_10m")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TZ)
    return parsed.astimezone(_DEFAULT_TZ).replace(microsecond=0)


def _parse_date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def _parse_clock(value: str) -> time:
    text = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"invalid course time: {value}")


def _actor_kind(src: str) -> str:
    if src in {"openclaw", "llm"}:
        return "llm"
    if src in {"system", "scheduler", "course-generator"}:
        return "system"
    if src in {"screen", "device"}:
        return "device"
    return "user"


def _record_action(
    db: Session,
    *,
    user_id: str,
    src: str,
    action: str,
    target_kind: str,
    target_id: str,
) -> None:
    db.add(
        ActLog(
            userId=user_id,
            actorKind=_actor_kind(src),
            actorId=src,
            action=action,
            targetKind=target_kind,
            targetId=target_id,
            result="ok",
        )
    )


def _ensure_user(db: Session, user_id: str = _DEFAULT_USER_ID) -> None:
    from app.server.new_core import crud

    crud.getCurrentUser(db, userId=user_id)


def _event_dict(base: EvtBase, **extra: Any) -> dict[str, Any]:
    result = {
        "evtId": base.evtId,
        "userId": base.userId,
        "title": base.title,
        "desc": base.desc,
        "evtType": base.evtType,
        "prio": base.prio,
        "stat": base.stat,
        "createdAt": base.createdAt,
        "updatedAt": base.updatedAt,
    }
    result.update(extra)
    return result


def _reminder_dict(base: EvtBase, remind: RemindEvt) -> dict[str, Any]:
    return _event_dict(
        base,
        planEvtId=remind.planEvtId,
        ddlEvtId=remind.ddlEvtId,
        remindKind=remind.remindKind,
        triggerTime=remind.triggerTime,
        offsetMin=remind.offsetMin,
        firedAt=remind.firedAt,
    )


def _plan_reminders(db: Session, plan_evt_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(EvtBase, RemindEvt)
        .join(RemindEvt, RemindEvt.evtId == EvtBase.evtId)
        .where(RemindEvt.planEvtId == plan_evt_id)
        .order_by(RemindEvt.triggerTime.asc())
    ).all()
    return [_reminder_dict(base, remind) for base, remind in rows]


def _ddl_reminders(db: Session, ddl_evt_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(EvtBase, RemindEvt)
        .join(RemindEvt, RemindEvt.evtId == EvtBase.evtId)
        .where(RemindEvt.ddlEvtId == ddl_evt_id)
        .order_by(RemindEvt.triggerTime.asc())
    ).all()
    return [_reminder_dict(base, remind) for base, remind in rows]


def _plan_dict(db: Session, base: EvtBase, plan: PlanEvt) -> dict[str, Any]:
    result = _event_dict(
        base,
        stTime=plan.stTime,
        durationMin=plan.durationMin,
        reminders=_plan_reminders(db, base.evtId),
    )
    course_link = db.scalar(select(CoursePlan).where(CoursePlan.planEvtId == base.evtId))
    if course_link is not None:
        course = db.get(CourseEvt, course_link.courseEvtId)
        result.update(
            {
                "courseEvtId": course_link.courseEvtId,
                "occurrenceDate": course_link.occurrenceDate,
                "sequenceNo": course_link.sequenceNo,
                "courseName": course.courseName if course else None,
                "generatedBy": "course",
            }
        )
    ddl_link = db.scalar(select(DdlPlan).where(DdlPlan.planEvtId == base.evtId))
    if ddl_link is not None:
        result.update(
            {
                "ddlEvtId": ddl_link.ddlEvtId,
                "planRole": ddl_link.planRole,
                "sortOrder": ddl_link.sortOrder,
                "generatedBy": "ddl",
            }
        )
    return result


def _ddl_dict(db: Session, base: EvtBase, ddl: DdlEvt) -> dict[str, Any]:
    links = db.scalars(
        select(DdlPlan)
        .where(DdlPlan.ddlEvtId == base.evtId)
        .order_by(DdlPlan.sortOrder.asc())
    ).all()
    plans: list[dict[str, Any]] = []
    for link in links:
        plan_base = db.get(EvtBase, link.planEvtId)
        plan = db.get(PlanEvt, link.planEvtId)
        if plan_base and plan:
            item = _plan_dict(db, plan_base, plan)
            item.update({"planRole": link.planRole, "sortOrder": link.sortOrder})
            plans.append(item)
    return _event_dict(
        base, endTime=ddl.endTime, hardDdl=ddl.hardDdl, plans=plans,
        ddlReminders=_ddl_reminders(db, base.evtId),
    )


def _course_occurrences(db: Session, course_evt_id: str) -> list[dict[str, Any]]:
    links = db.scalars(
        select(CoursePlan)
        .where(CoursePlan.courseEvtId == course_evt_id)
        .order_by(CoursePlan.occurrenceDate.asc(), CoursePlan.sequenceNo.asc())
    ).all()
    result: list[dict[str, Any]] = []
    for link in links:
        base = db.get(EvtBase, link.planEvtId)
        plan = db.get(PlanEvt, link.planEvtId)
        if base and plan:
            item = _plan_dict(db, base, plan)
            item.update(
                {
                    "occurrenceDate": link.occurrenceDate,
                    "sequenceNo": link.sequenceNo,
                }
            )
            result.append(item)
    return result


def _course_dict(db: Session, base: EvtBase, course: CourseEvt) -> dict[str, Any]:
    occurrences = _course_occurrences(db, base.evtId)
    now = datetime.now(_DEFAULT_TZ)
    next_occurrence = next(
        (
            item
            for item in occurrences
            if item.get("stat") == "todo"
            and item.get("stTime")
            and _parse_datetime(str(item["stTime"])) >= now
        ),
        None,
    )
    return _event_dict(
        base,
        courseName=course.courseName,
        teacher=course.teacher,
        location=course.location,
        stTime=course.stTime,
        endTime=course.endTime,
        stDate=course.stDate,
        endDate=course.endDate,
        weekDay=course.weekDay,
        startWeek=course.startWeek,
        endWeek=course.endWeek,
        weekMode=course.weekMode,
        occurrenceCount=len(occurrences),
        nextOccurrence=next_occurrence,
        plans=occurrences,
    )


def _normalize_weekday(value: Any) -> int:
    aliases = {
        "monday": 1,
        "mon": 1,
        "星期一": 1,
        "周一": 1,
        "tuesday": 2,
        "tue": 2,
        "星期二": 2,
        "周二": 2,
        "wednesday": 3,
        "wed": 3,
        "星期三": 3,
        "周三": 3,
        "thursday": 4,
        "thu": 4,
        "星期四": 4,
        "周四": 4,
        "friday": 5,
        "fri": 5,
        "星期五": 5,
        "周五": 5,
        "saturday": 6,
        "sat": 6,
        "星期六": 6,
        "周六": 6,
        "sunday": 7,
        "sun": 7,
        "星期日": 7,
        "星期天": 7,
        "周日": 7,
        "周天": 7,
    }
    if isinstance(value, str):
        text = value.strip().lower()
        if text in aliases:
            return aliases[text]
        try:
            value = int(text)
        except ValueError as exc:
            raise ValueError("weekDay must be Monday-Sunday or 1-7") from exc
    weekday = int(value)
    if weekday < 1 or weekday > 7:
        raise ValueError("weekDay must be between 1 and 7")
    return weekday


def expand_course_dates(
    *,
    st_date: str,
    end_date: str,
    week_day: Any,
    start_week: int | None = None,
    end_week: int | None = None,
    week_mode: str = "all",
    semester_start: date | None = None,
) -> list[date]:
    start = _parse_date(st_date)
    end = _parse_date(end_date)
    if end < start:
        raise ValueError("endDate must not be earlier than stDate")
    weekday = _normalize_weekday(week_day)
    mode = str(week_mode or "all").lower()
    if mode not in {"all", "odd", "even"}:
        raise ValueError("weekMode must be all, odd, or even")
    if start_week is not None and int(start_week) < 1:
        raise ValueError("startWeek must be greater than 0")
    if end_week is not None and int(end_week) < 1:
        raise ValueError("endWeek must be greater than 0")
    if start_week is not None and end_week is not None and int(end_week) < int(start_week):
        raise ValueError("endWeek must not be earlier than startWeek")

    anchor_day = semester_start or start
    anchor_monday = anchor_day - timedelta(days=anchor_day.isoweekday() - 1)
    first = start + timedelta(days=(weekday - start.isoweekday()) % 7)
    result: list[date] = []
    current = first
    while current <= end:
        week_number = ((current - anchor_monday).days // 7) + 1
        if start_week is not None and week_number < int(start_week):
            current += timedelta(days=7)
            continue
        if end_week is not None and week_number > int(end_week):
            current += timedelta(days=7)
            continue
        if mode == "odd" and week_number % 2 == 0:
            current += timedelta(days=7)
            continue
        if mode == "even" and week_number % 2 == 1:
            current += timedelta(days=7)
            continue
        result.append(current)
        current += timedelta(days=7)
    return result


def _course_description(course: CourseEvt, base: EvtBase) -> str | None:
    parts = [base.desc] if base.desc else []
    if course.teacher:
        parts.append(f"教师：{course.teacher}")
    if course.location:
        parts.append(f"地点：{course.location}")
    return "；".join(parts) or None


def _delete_plan_tree(db: Session, plan_evt_id: str) -> None:
    reminder_ids = db.scalars(
        select(RemindEvt.evtId).where(RemindEvt.planEvtId == plan_evt_id)
    ).all()
    for reminder_id in reminder_ids:
        reminder = db.get(RemindEvt, reminder_id)
        reminder_base = db.get(EvtBase, reminder_id)
        if reminder is not None:
            db.delete(reminder)
        if reminder_base is not None:
            db.delete(reminder_base)
    course_link = db.scalar(select(CoursePlan).where(CoursePlan.planEvtId == plan_evt_id))
    if course_link is not None:
        db.delete(course_link)
    ddl_link = db.scalar(select(DdlPlan).where(DdlPlan.planEvtId == plan_evt_id))
    if ddl_link is not None:
        db.delete(ddl_link)
    plan = db.get(PlanEvt, plan_evt_id)
    base = db.get(EvtBase, plan_evt_id)
    if plan is not None:
        db.delete(plan)
    if base is not None:
        db.delete(base)


def sync_plan_reminders(
    db: Session,
    plan_evt_id: str,
    *,
    reset_fired: bool = False,
) -> list[dict[str, Any]]:
    base = db.get(EvtBase, plan_evt_id)
    plan = db.get(PlanEvt, plan_evt_id)
    if base is None or plan is None:
        raise ValueError(f"plan not found: {plan_evt_id}")
    start = _parse_datetime(plan.stTime)
    end = start + timedelta(minutes=max(1, int(plan.durationMin)))
    specs = {
        "plan_start_10m": (
            start - timedelta(minutes=_REMINDER_OFFSET_MIN),
            f"{base.title} · 开始前 10 分钟",
            f"计划将在 10 分钟后开始：{start.isoformat()}",
        ),
        "plan_end_10m": (
            end - timedelta(minutes=_REMINDER_OFFSET_MIN),
            f"{base.title} · 结束前 10 分钟",
            f"计划将在 10 分钟后结束：{end.isoformat()}",
        ),
    }
    existing = {
        row.remindKind: row
        for row in db.scalars(
            select(RemindEvt).where(RemindEvt.planEvtId == plan_evt_id)
        ).all()
    }
    for kind, (trigger, title, content) in specs.items():
        remind = existing.get(kind)
        target_stat = "todo" if base.stat == "todo" else "cancelled"
        if remind is None:
            reminder_base = EvtBase(
                evtId=newId(),
                userId=base.userId,
                title=title,
                desc=content,
                evtType="remind",
                prio=base.prio,
                stat=target_stat,
                createdAt=nowIso(),
                updatedAt=nowIso(),
            )
            db.add(reminder_base)
            db.flush()
            db.add(
                RemindEvt(
                    evtId=reminder_base.evtId,
                    planEvtId=plan_evt_id,
                    remindKind=kind,
                    triggerTime=trigger.isoformat(),
                    offsetMin=_REMINDER_OFFSET_MIN,
                    firedAt=None,
                )
            )
            _record_action(
                db,
                user_id=base.userId,
                src="system",
                action="auto_create",
                target_kind="evt",
                target_id=reminder_base.evtId,
            )
            continue
        reminder_base = db.get(EvtBase, remind.evtId)
        changed = remind.triggerTime != trigger.isoformat()
        remind.triggerTime = trigger.isoformat()
        remind.offsetMin = _REMINDER_OFFSET_MIN
        if reset_fired or changed:
            remind.firedAt = None
        if reminder_base is not None:
            reminder_base.title = title
            reminder_base.desc = content
            reminder_base.prio = base.prio
            reminder_base.stat = target_stat if remind.firedAt is None else "done"
            reminder_base.updatedAt = nowIso()

    db.flush()
    return _plan_reminders(db, plan_evt_id)


def create_plan_event(
    db: Session,
    *,
    title: str,
    stTime: str,
    durationMin: int = 30,
    desc: str | None = None,
    prio: str = "mid",
    src: str = "api",
    userId: str = _DEFAULT_USER_ID,
    commit: bool = True,
) -> dict[str, Any]:
    _ensure_user(db, userId)
    clean_title = str(title).strip()
    if not clean_title:
        raise ValueError("title required")
    start = _parse_datetime(stTime)
    duration = int(durationMin)
    if duration <= 0:
        raise ValueError("durationMin must be greater than 0")
    now = nowIso()
    base = EvtBase(
        evtId=newId(),
        userId=userId,
        title=clean_title,
        desc=desc,
        evtType="plan",
        prio=prio,
        stat="todo",
        createdAt=now,
        updatedAt=now,
    )
    db.add(base)
    db.flush()
    plan = PlanEvt(evtId=base.evtId, stTime=start.isoformat(), durationMin=duration)
    db.add(plan)
    db.flush()
    sync_plan_reminders(db, base.evtId)
    _record_action(
        db,
        user_id=userId,
        src=src,
        action="create",
        target_kind="planEvt",
        target_id=base.evtId,
    )
    if commit:
        db.commit()
    return _plan_dict(db, base, plan)


def _course_plan_spec(course: CourseEvt, base: EvtBase, occurrence: date, sequence: int) -> dict[str, Any]:
    start_clock = _parse_clock(course.stTime)
    end_clock = _parse_clock(course.endTime)
    start = datetime.combine(occurrence, start_clock, tzinfo=_DEFAULT_TZ)
    end = datetime.combine(occurrence, end_clock, tzinfo=_DEFAULT_TZ)
    if end <= start:
        raise ValueError("course endTime must be later than stTime")
    return {
        "title": course.courseName or base.title,
        "desc": _course_description(course, base),
        "stTime": start.isoformat(),
        "durationMin": int((end - start).total_seconds() // 60),
        "occurrenceDate": occurrence.isoformat(),
        "sequenceNo": sequence,
    }


def sync_course_plans(db: Session, course_evt_id: str) -> list[dict[str, Any]]:
    base = db.get(EvtBase, course_evt_id)
    course = db.get(CourseEvt, course_evt_id)
    if base is None or course is None:
        raise ValueError(f"course not found: {course_evt_id}")
    semester_start = get_settings().semester_start
    desired_dates = expand_course_dates(
        st_date=course.stDate,
        end_date=course.endDate,
        week_day=course.weekDay,
        start_week=course.startWeek,
        end_week=course.endWeek,
        week_mode=course.weekMode,
        semester_start=semester_start,
    )
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
        if occurrence_date in desired_keys:
            continue
        _delete_plan_tree(db, link.planEvtId)

    db.flush()
    return _course_occurrences(db, course_evt_id)


def create_course_event(
    db: Session,
    *,
    courseName: str,
    stTime: str,
    endTime: str,
    stDate: str,
    endDate: str,
    weekDay: Any,
    title: str | None = None,
    teacher: str | None = None,
    location: str | None = None,
    startWeek: int | None = None,
    endWeek: int | None = None,
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
    expand_course_dates(
        st_date=stDate,
        end_date=endDate,
        week_day=weekday,
        start_week=startWeek,
        end_week=endWeek,
        week_mode=weekMode,
        semester_start=get_settings().semester_start,
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
        stDate=_parse_date(stDate).isoformat(),
        endDate=_parse_date(endDate).isoformat(),
        weekDay=weekday,
        startWeek=int(startWeek) if startWeek is not None else None,
        endWeek=int(endWeek) if endWeek is not None else None,
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
    return _course_dict(db, base, course)


def update_course_event(db: Session, course_evt_id: str, *, src: str = "api", **fields: Any) -> dict[str, Any]:
    base = db.get(EvtBase, course_evt_id)
    course = db.get(CourseEvt, course_evt_id)
    if base is None or course is None:
        raise ValueError(f"course not found: {course_evt_id}")
    for key in ("title", "desc", "prio", "stat"):
        if key in fields and fields[key] is not None:
            setattr(base, key, fields[key])
    if "courseName" in fields and fields["courseName"] is not None:
        clean_name = str(fields["courseName"]).strip()
        if not clean_name:
            raise ValueError("courseName required")
        course.courseName = clean_name
        if "title" not in fields:
            base.title = clean_name
    for key in ("teacher", "location"):
        if key in fields:
            setattr(course, key, fields[key] or None)
    if "stTime" in fields and fields["stTime"] is not None:
        _parse_clock(str(fields["stTime"]))
        course.stTime = str(fields["stTime"])[:8]
    if "endTime" in fields and fields["endTime"] is not None:
        _parse_clock(str(fields["endTime"]))
        course.endTime = str(fields["endTime"])[:8]
    if "stDate" in fields and fields["stDate"] is not None:
        course.stDate = _parse_date(str(fields["stDate"])).isoformat()
    if "endDate" in fields and fields["endDate"] is not None:
        course.endDate = _parse_date(str(fields["endDate"])).isoformat()
    if "weekDay" in fields and fields["weekDay"] is not None:
        course.weekDay = _normalize_weekday(fields["weekDay"])
    if "startWeek" in fields:
        course.startWeek = int(fields["startWeek"]) if fields["startWeek"] not in (None, "") else None
    if "endWeek" in fields:
        course.endWeek = int(fields["endWeek"]) if fields["endWeek"] not in (None, "") else None
    if "weekMode" in fields and fields["weekMode"] is not None:
        course.weekMode = str(fields["weekMode"]).lower()
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
    return _course_dict(db, base, course)


def update_event(db: Session, evt_id: str, *, src: str = "api", **fields: Any) -> dict[str, Any]:
    base = db.get(EvtBase, evt_id)
    if base is None:
        raise ValueError(f"evt not found: {evt_id}")
    if base.evtType == "course":
        return update_course_event(db, evt_id, src=src, **fields)
    if base.evtType == "remind":
        raise ValueError("reminder events are managed automatically")
    for key in ("title", "desc", "prio", "stat"):
        if key in fields and fields[key] is not None:
            setattr(base, key, fields[key])
    if base.evtType == "plan":
        plan = db.get(PlanEvt, evt_id)
        if plan is None:
            raise ValueError(f"plan not found: {evt_id}")
        changed = False
        if "stTime" in fields and fields["stTime"] is not None:
            normalized = _parse_datetime(str(fields["stTime"])).isoformat()
            changed = changed or normalized != plan.stTime
            plan.stTime = normalized
        if "durationMin" in fields and fields["durationMin"] is not None:
            duration = int(fields["durationMin"])
            if duration <= 0:
                raise ValueError("durationMin must be greater than 0")
            changed = changed or duration != plan.durationMin
            plan.durationMin = duration
        sync_plan_reminders(db, evt_id, reset_fired=changed)
    elif base.evtType == "ddl":
        ddl = db.get(DdlEvt, evt_id)
        if ddl is None:
            raise ValueError(f"ddl not found: {evt_id}")
        if "endTime" in fields and fields["endTime"] is not None:
            ddl.endTime = _parse_datetime(str(fields["endTime"])).isoformat()
        if "hardDdl" in fields and fields["hardDdl"] is not None:
            ddl.hardDdl = bool(fields["hardDdl"])
    base.updatedAt = nowIso()
    _record_action(
        db,
        user_id=base.userId,
        src=src,
        action="update",
        target_kind="evt",
        target_id=evt_id,
    )
    db.commit()
    return get_event(db, evt_id)


def update_commute_plan(
    db: Session,
    *,
    plan_evt_id: str,
    reminder_evt_id: str,
    departure_at: str,
    commute_minutes: int,
    end_at: str,
    user_id: str,
    src: str = "api",
) -> dict[str, Any]:
    plan_base = db.get(EvtBase, plan_evt_id)
    if plan_base is None or plan_base.userId != user_id:
        raise ValueError(f"plan not found: {plan_evt_id}")
    plan = db.get(PlanEvt, plan_evt_id)
    if plan_base.evtType != "plan" or plan is None:
        raise ValueError(f"event is not a plan: {plan_evt_id}")
    if plan_base.stat == "cancelled":
        raise ValueError("commute plan is cancelled")

    reminder_base = db.get(EvtBase, reminder_evt_id)
    if reminder_base is None or reminder_base.userId != user_id:
        raise ValueError(f"reminder not found: {reminder_evt_id}")
    reminder = db.get(RemindEvt, reminder_evt_id)
    if reminder_base.evtType != "remind" or reminder is None:
        raise ValueError(f"event is not a reminder: {reminder_evt_id}")
    if (
        reminder.planEvtId is not None
        or reminder.ddlEvtId is not None
        or reminder.remindKind != "manual"
    ):
        raise ValueError("departure reminder must be an existing standalone manual reminder")
    if reminder_base.stat == "cancelled":
        raise ValueError("departure reminder is cancelled")

    if isinstance(commute_minutes, bool):
        raise ValueError("commuteMinutes must be an integer")
    minutes = int(commute_minutes)
    if isinstance(commute_minutes, float) and commute_minutes != minutes:
        raise ValueError("commuteMinutes must be an integer")
    if minutes < 0 or minutes > 1440:
        raise ValueError("commuteMinutes must be between 0 and 1440")
    departure = _parse_datetime(departure_at)
    arrival = departure + timedelta(minutes=minutes)
    end = _parse_datetime(end_at)
    if end <= arrival:
        raise ValueError("endAt must be later than departureAt plus commuteMinutes")
    duration_seconds = int((end - arrival).total_seconds())
    if duration_seconds % 60:
        raise ValueError("endAt and arrival time must align to whole minutes")

    try:
        plan_changed = plan.stTime != arrival.isoformat() or plan.durationMin != duration_seconds // 60
        plan.stTime = arrival.isoformat()
        plan.durationMin = duration_seconds // 60
        plan_base.updatedAt = nowIso()
        sync_plan_reminders(db, plan_evt_id, reset_fired=plan_changed)

        reminder.triggerTime = departure.isoformat()
        reminder.firedAt = None
        if reminder_base.stat == "done":
            reminder_base.stat = "todo"
        reminder_base.updatedAt = nowIso()

        _record_action(
            db,
            user_id=user_id,
            src=src,
            action="update",
            target_kind="evt",
            target_id=plan_evt_id,
        )
        _record_action(
            db,
            user_id=user_id,
            src=src,
            action="update",
            target_kind="evt",
            target_id=reminder_evt_id,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "departureAt": departure.isoformat(),
        "arrivalAt": arrival.isoformat(),
        "endAt": end.isoformat(),
        "commuteMinutes": minutes,
        "plan": get_event(db, plan_evt_id),
        "reminder": get_event(db, reminder_evt_id, include_reminders=True),
    }


def cancel_event(db: Session, evt_id: str, *, src: str = "api") -> dict[str, Any]:
    base = db.get(EvtBase, evt_id)
    if base is None:
        raise ValueError(f"evt not found: {evt_id}")
    base.stat = "cancelled"
    base.updatedAt = nowIso()
    if base.evtType == "plan":
        for reminder_base, _ in db.execute(
            select(EvtBase, RemindEvt)
            .join(RemindEvt, RemindEvt.evtId == EvtBase.evtId)
            .where(RemindEvt.planEvtId == evt_id)
        ).all():
            reminder_base.stat = "cancelled"
            reminder_base.updatedAt = nowIso()
    elif base.evtType == "course":
        for link in db.scalars(select(CoursePlan).where(CoursePlan.courseEvtId == evt_id)).all():
            plan_base = db.get(EvtBase, link.planEvtId)
            if plan_base is not None:
                plan_base.stat = "cancelled"
                plan_base.updatedAt = nowIso()
                sync_plan_reminders(db, plan_base.evtId)
    elif base.evtType == "ddl":
        for link in db.scalars(select(DdlPlan).where(DdlPlan.ddlEvtId == evt_id)).all():
            plan_base = db.get(EvtBase, link.planEvtId)
            if plan_base is not None:
                plan_base.stat = "cancelled"
                plan_base.updatedAt = nowIso()
                sync_plan_reminders(db, plan_base.evtId)
        for reminder_base, _ in db.execute(
            select(EvtBase, RemindEvt)
            .join(RemindEvt, RemindEvt.evtId == EvtBase.evtId)
            .where(RemindEvt.ddlEvtId == evt_id)
        ).all():
            reminder_base.stat = "cancelled"
            reminder_base.updatedAt = nowIso()
    _record_action(
        db,
        user_id=base.userId,
        src=src,
        action="cancel",
        target_kind="evt",
        target_id=evt_id,
    )
    db.commit()
    return get_event(db, evt_id, include_reminders=base.evtType == "remind")


def get_event(db: Session, evt_id: str, *, include_reminders: bool = False) -> dict[str, Any]:
    base = db.get(EvtBase, evt_id)
    if base is None:
        raise ValueError(f"evt not found: {evt_id}")
    if base.evtType == "plan":
        plan = db.get(PlanEvt, evt_id)
        if plan is None:
            raise ValueError(f"plan not found: {evt_id}")
        return _plan_dict(db, base, plan)
    if base.evtType == "ddl":
        ddl = db.get(DdlEvt, evt_id)
        if ddl is None:
            raise ValueError(f"ddl not found: {evt_id}")
        return _ddl_dict(db, base, ddl)
    if base.evtType == "course":
        course = db.get(CourseEvt, evt_id)
        if course is None:
            raise ValueError(f"course not found: {evt_id}")
        return _course_dict(db, base, course)
    if base.evtType == "remind" and include_reminders:
        remind = db.get(RemindEvt, evt_id)
        if remind is None:
            raise ValueError(f"reminder not found: {evt_id}")
        return _reminder_dict(base, remind)
    raise ValueError(f"unsupported evtType: {base.evtType}")


def _event_in_range(item: dict[str, Any], start: datetime | None, end: datetime | None) -> bool:
    if start is None and end is None:
        return True
    if item.get("evtType") == "course":
        try:
            course_start = _parse_date(str(item.get("stDate") or ""))
            course_end = _parse_date(str(item.get("endDate") or ""))
            weekday = int(item.get("weekDay"))
        except (TypeError, ValueError):
            return False
        left = max(course_start, start.date() if start else course_start)
        right = min(course_end, end.date() if end else course_end)
        if left > right:
            return False
        first_match = left + timedelta(days=(weekday - left.isoweekday()) % 7)
        return first_match <= right
    raw = item.get("stTime") or item.get("endTime") or item.get("triggerTime")
    if not raw:
        return False
    instant = _parse_datetime(str(raw))
    item_end = instant
    if item.get("evtType") == "plan":
        item_end = instant + timedelta(minutes=int(item.get("durationMin") or 0))
    if start is not None and item_end < start:
        return False
    if end is not None and instant > end:
        return False
    return True


def list_events(
    db: Session,
    *,
    user_id: str = _DEFAULT_USER_ID,
    include_reminders: bool = False,
    date_value: str | None = None,
    evt_types: Iterable[str] | None = None,
    stats: Iterable[str] | None = None,
    text: str | None = None,
    start: str | None = None,
    end: str | None = None,
    include_course_templates: bool = True,
) -> list[dict[str, Any]]:
    allowed_types = {str(item) for item in evt_types or []}
    allowed_stats = {str(item) for item in stats or []}
    start_dt = _parse_datetime(start) if start else None
    end_dt = _parse_datetime(end) if end else None
    if date_value:
        target = _parse_date(date_value)
        start_dt = datetime.combine(target, time.min, tzinfo=_DEFAULT_TZ)
        end_dt = datetime.combine(target, time.max, tzinfo=_DEFAULT_TZ)
    rows = db.scalars(
        select(EvtBase)
        .where(EvtBase.userId == user_id)
        .order_by(EvtBase.createdAt.asc())
    ).all()
    result: list[dict[str, Any]] = []
    query_text = str(text or "").strip().lower()
    for base in rows:
        if base.evtType == "remind" and not include_reminders:
            continue
        if (
            base.evtType == "course"
            and (date_value or start_dt is not None or end_dt is not None)
            and not include_course_templates
        ):
            continue
        if allowed_types and base.evtType not in allowed_types:
            continue
        if allowed_stats and base.stat not in allowed_stats:
            continue
        try:
            item = get_event(db, base.evtId, include_reminders=include_reminders)
        except ValueError:
            continue
        if query_text and query_text not in f"{item.get('title', '')} {item.get('desc', '')}".lower():
            continue
        if not _event_in_range(item, start_dt, end_dt):
            continue
        result.append(item)
    return result


def list_course_events(db: Session, *, user_id: str = _DEFAULT_USER_ID) -> list[dict[str, Any]]:
    rows = db.execute(
        select(EvtBase, CourseEvt)
        .join(CourseEvt, CourseEvt.evtId == EvtBase.evtId)
        .where(EvtBase.userId == user_id)
        .order_by(CourseEvt.weekDay.asc(), CourseEvt.stTime.asc())
    ).all()
    return [_course_dict(db, base, course) for base, course in rows]


def list_reminder_events(db: Session, *, user_id: str = _DEFAULT_USER_ID) -> list[dict[str, Any]]:
    rows = db.execute(
        select(EvtBase, RemindEvt)
        .join(RemindEvt, RemindEvt.evtId == EvtBase.evtId)
        .where(EvtBase.userId == user_id)
        .order_by(RemindEvt.triggerTime.asc())
    ).all()
    return [_reminder_dict(base, remind) for base, remind in rows]


def query_events(db: Session, body: dict[str, Any]) -> dict[str, Any]:
    raw_types = body.get("evtType") or body.get("evtTypes")
    evt_types = [raw_types] if isinstance(raw_types, str) else raw_types
    if evt_types:
        evt_types = ["plan" if str(item) == "life" else str(item) for item in evt_types]
    raw_stats = body.get("stat") or body.get("stats")
    stats = [raw_stats] if isinstance(raw_stats, str) else raw_stats
    time_range = body.get("timeRange") or body.get("time_range") or {}
    rows = list_events(
        db,
        user_id=str(body.get("userId") or _DEFAULT_USER_ID),
        include_reminders=bool(body.get("includeReminders", False)),
        date_value=body.get("date"),
        evt_types=evt_types,
        stats=stats,
        text=body.get("text") or body.get("keyword"),
        start=time_range.get("start") if isinstance(time_range, dict) else None,
        end=time_range.get("end") if isinstance(time_range, dict) else None,
        include_course_templates=bool(body.get("includeCourseTemplates", True)),
    )
    evt_id = body.get("evtId") or body.get("eventId")
    if evt_id:
        rows = [item for item in rows if item.get("evtId") == evt_id]
    if body.get("includePlans", True) is False:
        rows = [item for item in rows if item.get("evtType") != "plan"]
    if not bool(body.get("includeLinkedPlans", False)):
        rows = [
            item
            for item in rows
            if not (item.get("evtType") == "plan" and item.get("generatedBy") in {"ddl", "course"})
        ]
    limit = max(1, min(500, int(body.get("limit") or 100)))
    return {"items": rows[:limit], "count": min(len(rows), limit), "total": len(rows)}


def apply_reminder_action(
    db: Session,
    *,
    evt_id: str,
    action: str,
    now: str,
    src: str,
) -> dict[str, Any]:
    base = db.get(EvtBase, evt_id)
    if base is None:
        raise ValueError(f"evt not found: {evt_id}")
    target_id = evt_id
    if base.evtType == "remind":
        remind = db.get(RemindEvt, evt_id)
        if remind is None:
            raise ValueError(f"reminder not found: {evt_id}")
        target_id = remind.planEvtId
        base = db.get(EvtBase, target_id)
        if base is None:
            raise ValueError(f"plan not found: {target_id}")
    if base.evtType != "plan":
        raise ValueError(f"reminder action requires a plan event: {target_id}")
    if action == "done":
        return update_event(db, target_id, src=src, stat="done")
    if action == "snooze10":
        plan = db.get(PlanEvt, target_id)
        if plan is None:
            raise ValueError(f"plan not found: {target_id}")
        new_start = _parse_datetime(now) + timedelta(minutes=10)
        return update_event(db, target_id, src=src, stTime=new_start.isoformat())
    raise ValueError(f"unknown reminder action: {action}")


def mark_reminder_fired(db: Session, reminder_evt_id: str, *, fired_at: str) -> None:
    base = db.get(EvtBase, reminder_evt_id)
    remind = db.get(RemindEvt, reminder_evt_id)
    if base is None or remind is None:
        return
    remind.firedAt = _parse_datetime(fired_at).isoformat()
    base.stat = "done"
    base.updatedAt = nowIso()
    db.flush()


def ensure_all_relations(db: Session) -> dict[str, int]:
    reminder_count = 0
    course_plan_count = 0
    for plan_evt_id in db.scalars(select(PlanEvt.evtId)).all():
        sync_plan_reminders(db, plan_evt_id)
        reminder_count += 2
    for course_evt_id in db.scalars(select(CourseEvt.evtId)).all():
        course_plan_count += len(sync_course_plans(db, course_evt_id))
    db.commit()
    return {"reminders": reminder_count, "coursePlans": course_plan_count}
