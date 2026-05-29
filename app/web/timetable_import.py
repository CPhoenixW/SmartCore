from __future__ import annotations

import csv
from io import StringIO

from sqlalchemy.orm import Session

from app.db import crud
from app.db.models import Course, WeekRule

CSV_HEADERS = (
    "course_name",
    "teacher",
    "default_location",
    "weekday",
    "start_time",
    "end_time",
    "week_rule",
    "week_range",
    "location_override",
)


def _parse_week_rule(value: str) -> WeekRule:
    normalized = (value or "every").strip().lower()
    for rule in WeekRule:
        if rule.value == normalized:
            return rule
    raise ValueError(f"invalid week_rule: {value}")


def _get_or_create_course(
    db: Session,
    *,
    name: str,
    teacher: str | None,
    default_location: str | None,
) -> Course:
    course = db.query(Course).filter(Course.name == name).first()
    if course:
        return course
    return crud.create_course(
        db,
        name=name,
        teacher=teacher or None,
        default_location=default_location or None,
    )


def import_timetable_csv(db: Session, content: str) -> tuple[int, int, list[str]]:
    """Import timetable rows from CSV text. Returns (courses, sessions, errors)."""
    reader = csv.DictReader(StringIO(content.strip()))
    if reader.fieldnames is None:
        return 0, 0, ["CSV 内容为空"]

    missing = [header for header in CSV_HEADERS if header not in reader.fieldnames]
    if missing:
        return 0, 0, [f"缺少 CSV 列: {', '.join(missing)}"]

    courses_created = 0
    sessions_created = 0
    errors: list[str] = []

    for line_no, row in enumerate(reader, start=2):
        course_name = (row.get("course_name") or "").strip()
        if not course_name:
            errors.append(f"第 {line_no} 行: course_name 不能为空")
            continue

        weekday_raw = (row.get("weekday") or "").strip()
        try:
            weekday = int(weekday_raw)
            if weekday < 1 or weekday > 7:
                raise ValueError("weekday out of range")
        except ValueError:
            errors.append(f"第 {line_no} 行: weekday 必须是 1-7")
            continue

        try:
            week_rule = _parse_week_rule(row.get("week_rule", "every"))
        except ValueError as exc:
            errors.append(f"第 {line_no} 行: {exc}")
            continue

        existing_course = db.query(Course).filter(Course.name == course_name).first()
        course = _get_or_create_course(
            db,
            name=course_name,
            teacher=(row.get("teacher") or "").strip() or None,
            default_location=(row.get("default_location") or "").strip() or None,
        )
        if existing_course is None:
            courses_created += 1

        crud.create_course_session(
            db,
            course_id=course.id,
            weekday=weekday,
            start_time=(row.get("start_time") or "").strip() or None,
            end_time=(row.get("end_time") or "").strip() or None,
            week_rule=week_rule,
            week_range=(row.get("week_range") or "").strip() or None,
            location_override=(row.get("location_override") or "").strip() or None,
        )
        sessions_created += 1

    return courses_created, sessions_created, errors
