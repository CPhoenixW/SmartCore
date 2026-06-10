from __future__ import annotations

import csv
from io import StringIO

from sqlalchemy.orm import Session

from app.db import crud
from app.db.models import Assignment, Course, CourseSession, WeekRule

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


def _validate_timetable_row(
    line_no: int,
    row: dict[str, str | None],
) -> tuple[dict | None, str | None]:
    course_name = (row.get("course_name") or "").strip()
    if not course_name:
        return None, f"第 {line_no} 行: course_name 不能为空"

    weekday_raw = (row.get("weekday") or "").strip()
    try:
        weekday = int(weekday_raw)
        if weekday < 1 or weekday > 7:
            raise ValueError("weekday out of range")
    except ValueError:
        return None, f"第 {line_no} 行: weekday 必须是 1-7"

    try:
        week_rule = _parse_week_rule(row.get("week_rule", "every"))
    except ValueError as exc:
        return None, f"第 {line_no} 行: {exc}"

    return {
        "course_name": course_name,
        "teacher": (row.get("teacher") or "").strip() or None,
        "default_location": (row.get("default_location") or "").strip() or None,
        "weekday": weekday,
        "start_time": (row.get("start_time") or "").strip() or None,
        "end_time": (row.get("end_time") or "").strip() or None,
        "week_rule": week_rule,
        "week_range": (row.get("week_range") or "").strip() or None,
        "location_override": (row.get("location_override") or "").strip() or None,
    }, None


def _clear_timetable(db: Session) -> None:
    db.query(Assignment).filter(Assignment.course_id.isnot(None)).update(
        {Assignment.course_id: None},
        synchronize_session=False,
    )
    db.query(CourseSession).delete()
    db.query(Course).delete()
    db.commit()


def import_timetable_csv(db: Session, content: str) -> tuple[int, int, list[str]]:
    """Import timetable rows from CSV text. Returns (courses, sessions, errors)."""
    reader = csv.DictReader(StringIO(content.strip()))
    if reader.fieldnames is None:
        return 0, 0, ["CSV 内容为空"]

    missing = [header for header in CSV_HEADERS if header not in reader.fieldnames]
    if missing:
        return 0, 0, [f"缺少 CSV 列: {', '.join(missing)}"]

    validated_rows: list[dict] = []
    errors: list[str] = []

    for line_no, row in enumerate(reader, start=2):
        parsed, error = _validate_timetable_row(line_no, row)
        if error:
            errors.append(error)
            continue
        validated_rows.append(parsed)

    if errors:
        return 0, 0, errors

    _clear_timetable(db)

    courses_created = 0
    sessions_created = 0
    course_cache: dict[str, Course] = {}

    for row in validated_rows:
        course_name = row["course_name"]
        course = course_cache.get(course_name)
        if course is None:
            course = crud.create_course(
                db,
                name=course_name,
                teacher=row["teacher"],
                default_location=row["default_location"],
            )
            course_cache[course_name] = course
            courses_created += 1

        crud.create_course_session(
            db,
            course_id=course.id,
            weekday=row["weekday"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            week_rule=row["week_rule"],
            week_range=row["week_range"],
            location_override=row["location_override"],
        )
        sessions_created += 1

    return courses_created, sessions_created, []
