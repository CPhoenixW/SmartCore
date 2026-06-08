from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.actions.executor import ActionExecutor
from app.config import get_settings
from app.db import crud
from app.db.models import (
    Assignment,
    AssignmentStatus,
    Course,
    LifeEvent,
    LifeEventStatus,
    MessageLog,
    PendingOperation,
    PendingOperationStatus,
    Reminder,
    ReminderStatus,
)
from app.db.session import get_db
from app.operations.parser import RuleBasedOperationParser
from app.secretary.planner import build_today_plan, build_tomorrow_plan
from app.secretary.rules import DEFAULT_TZ
from app.web.timetable_import import CSV_HEADERS, import_timetable_csv

WEB_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


def _pretty_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _short_id(value: object, prefix: int = 10, suffix: int = 6) -> str:
    text = str(value or "")
    if len(text) <= prefix + suffix + 1:
        return text
    return f"{text[:prefix]}...{text[-suffix:]}"


templates.env.filters["pretty_json"] = _pretty_json
templates.env.filters["short_id"] = _short_id


def _parse_datetime_local(value: str | None, tz: ZoneInfo) -> datetime | None:
    if not value or not value.strip():
        return None
    parsed = datetime.fromisoformat(value.strip())
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def create_web_router() -> APIRouter:
    router = APIRouter(prefix="/dashboard", tags=["web"])

    @router.get("", include_in_schema=False)
    def dashboard_root() -> RedirectResponse:
        return RedirectResponse(url="/dashboard/today", status_code=303)

    @router.get("/today", response_class=HTMLResponse)
    def today_plan(
        request: Request,
        db: Session = Depends(get_db),
    ) -> HTMLResponse:
        settings = get_settings()
        plan = build_today_plan(
            db,
            tz=DEFAULT_TZ,
            semester_start=settings.semester_start,
        )
        pending_operations_count = (
            db.query(PendingOperation)
            .filter(PendingOperation.status == PendingOperationStatus.PENDING.value)
            .count()
        )
        pending_reminders_count = (
            db.query(Reminder)
            .filter(Reminder.status == ReminderStatus.PENDING.value)
            .count()
        )
        next_reminder = (
            db.query(Reminder)
            .filter(Reminder.status == ReminderStatus.PENDING.value)
            .order_by(Reminder.scheduled_at.asc())
            .first()
        )
        return templates.TemplateResponse(
            request,
            "today.html",
            {
                "active_page": "today",
                "plan": plan,
                "today": plan.target_date,
                "plan_label": "今日",
                "pending_operations_count": pending_operations_count,
                "pending_reminders_count": pending_reminders_count,
                "next_reminder": next_reminder,
            },
        )

    @router.get("/tomorrow", response_class=HTMLResponse)
    def tomorrow_plan(
        request: Request,
        db: Session = Depends(get_db),
    ) -> HTMLResponse:
        settings = get_settings()
        plan = build_tomorrow_plan(
            db,
            tz=DEFAULT_TZ,
            semester_start=settings.semester_start,
        )
        return templates.TemplateResponse(
            request,
            "tomorrow.html",
            {
                "active_page": "tomorrow",
                "plan": plan,
                "plan_label": "明日",
            },
        )

    @router.get("/timetable", response_class=HTMLResponse)
    def timetable_import_page(request: Request) -> HTMLResponse:
        sample = ",".join(CSV_HEADERS)
        return templates.TemplateResponse(
            request,
            "timetable_import.html",
            {
                "active_page": "timetable",
                "csv_headers": CSV_HEADERS,
                "sample_row": sample,
                "message": None,
                "errors": [],
            },
        )

    @router.post("/timetable", response_class=HTMLResponse)
    def timetable_import_submit(
        request: Request,
        csv_content: str = Form(...),
        db: Session = Depends(get_db),
    ) -> HTMLResponse:
        courses_created, sessions_created, errors = import_timetable_csv(db, csv_content)
        if errors:
            message = None
        else:
            message = f"导入完成：{courses_created} 门课程，{sessions_created} 个时段。"
        return templates.TemplateResponse(
            request,
            "timetable_import.html",
            {
                "active_page": "timetable",
                "csv_headers": CSV_HEADERS,
                "sample_row": ",".join(CSV_HEADERS),
                "message": message,
                "errors": errors,
                "csv_content": csv_content,
            },
        )

    @router.get("/assignments", response_class=HTMLResponse)
    def assignments_page(
        request: Request,
        db: Session = Depends(get_db),
    ) -> HTMLResponse:
        assignments = (
            db.query(Assignment)
            .options(joinedload(Assignment.course))
            .order_by(Assignment.due_at.asc().nullslast(), Assignment.created_at.desc())
            .all()
        )
        courses = db.query(Course).order_by(Course.name.asc()).all()
        return templates.TemplateResponse(
            request,
            "assignments.html",
            {
                "active_page": "assignments",
                "assignments": assignments,
                "courses": courses,
                "message": None,
            },
        )

    @router.post("/assignments", response_class=HTMLResponse)
    def create_assignment(
        request: Request,
        title: str = Form(...),
        due_at: str = Form(""),
        course_id: str = Form(""),
        notes: str = Form(""),
        db: Session = Depends(get_db),
    ) -> HTMLResponse:
        parsed_course_id = int(course_id) if course_id.strip() else None
        parsed_due_at = _parse_datetime_local(due_at, DEFAULT_TZ)
        crud.create_assignment(
            db,
            title=title.strip(),
            course_id=parsed_course_id,
            due_at=parsed_due_at,
            notes=notes.strip() or None,
        )
        assignments = (
            db.query(Assignment)
            .options(joinedload(Assignment.course))
            .order_by(Assignment.due_at.asc().nullslast(), Assignment.created_at.desc())
            .all()
        )
        courses = db.query(Course).order_by(Course.name.asc()).all()
        return templates.TemplateResponse(
            request,
            "assignments.html",
            {
                "active_page": "assignments",
                "assignments": assignments,
                "courses": courses,
                "message": f"已添加作业：{title.strip()}",
            },
        )

    @router.post("/assignments/{assignment_id}/complete")
    def complete_assignment(
        assignment_id: int,
        db: Session = Depends(get_db),
    ) -> RedirectResponse:
        assignment = db.get(Assignment, assignment_id)
        if assignment:
            assignment.status = AssignmentStatus.DONE.value
            db.commit()
        return RedirectResponse(url="/dashboard/assignments", status_code=303)

    @router.get("/life-events", response_class=HTMLResponse)
    def life_events_page(
        request: Request,
        db: Session = Depends(get_db),
    ) -> HTMLResponse:
        events = (
            db.query(LifeEvent)
            .order_by(LifeEvent.scheduled_at.asc().nullslast(), LifeEvent.created_at.desc())
            .all()
        )
        return templates.TemplateResponse(
            request,
            "life_events.html",
            {
                "active_page": "life_events",
                "events": events,
                "message": None,
            },
        )

    @router.post("/life-events", response_class=HTMLResponse)
    def create_life_event(
        request: Request,
        title: str = Form(...),
        scheduled_at: str = Form(""),
        deadline_at: str = Form(""),
        notes: str = Form(""),
        db: Session = Depends(get_db),
    ) -> HTMLResponse:
        crud.create_life_event(
            db,
            title=title.strip(),
            scheduled_at=_parse_datetime_local(scheduled_at, DEFAULT_TZ),
            deadline_at=_parse_datetime_local(deadline_at, DEFAULT_TZ),
            notes=notes.strip() or None,
        )
        events = (
            db.query(LifeEvent)
            .order_by(LifeEvent.scheduled_at.asc().nullslast(), LifeEvent.created_at.desc())
            .all()
        )
        return templates.TemplateResponse(
            request,
            "life_events.html",
            {
                "active_page": "life_events",
                "events": events,
                "message": f"已添加事项：{title.strip()}",
            },
        )

    @router.post("/life-events/{event_id}/complete")
    def complete_life_event(
        event_id: int,
        db: Session = Depends(get_db),
    ) -> RedirectResponse:
        event = db.get(LifeEvent, event_id)
        if event:
            event.status = LifeEventStatus.DONE.value
            db.commit()
        return RedirectResponse(url="/dashboard/life-events", status_code=303)

    @router.get("/reminders", response_class=HTMLResponse)
    def reminders_page(
        request: Request,
        db: Session = Depends(get_db),
    ) -> HTMLResponse:
        reminders = (
            db.query(Reminder)
            .order_by(Reminder.scheduled_at.desc(), Reminder.created_at.desc())
            .limit(200)
            .all()
        )
        status_counts = {
            ReminderStatus.PENDING.value: db.query(Reminder)
            .filter(Reminder.status == ReminderStatus.PENDING.value)
            .count(),
            ReminderStatus.SENT.value: db.query(Reminder)
            .filter(Reminder.status == ReminderStatus.SENT.value)
            .count(),
            ReminderStatus.FAILED.value: db.query(Reminder)
            .filter(Reminder.status == ReminderStatus.FAILED.value)
            .count(),
        }
        next_reminder = (
            db.query(Reminder)
            .filter(Reminder.status == ReminderStatus.PENDING.value)
            .order_by(Reminder.scheduled_at.asc())
            .first()
        )
        return templates.TemplateResponse(
            request,
            "reminders.html",
            {
                "active_page": "reminders",
                "reminders": reminders,
                "status_counts": status_counts,
                "next_reminder": next_reminder,
            },
        )

    @router.post("/reminders/{reminder_id}/cancel")
    def cancel_reminder(
        reminder_id: int,
        db: Session = Depends(get_db),
    ) -> RedirectResponse:
        reminder = db.get(Reminder, reminder_id)
        if reminder and reminder.status == ReminderStatus.PENDING.value:
            reminder.status = ReminderStatus.CANCELLED.value
            db.commit()
        return RedirectResponse(url="/dashboard/reminders", status_code=303)

    @router.post("/reminders/{reminder_id}/update")
    def update_reminder(
        reminder_id: int,
        scheduled_at: str = Form(...),
        db: Session = Depends(get_db),
    ) -> RedirectResponse:
        reminder = db.get(Reminder, reminder_id)
        if reminder and reminder.status == ReminderStatus.PENDING.value:
            parsed = _parse_datetime_local(scheduled_at, DEFAULT_TZ)
            if parsed:
                reminder.scheduled_at = parsed
                db.commit()
        return RedirectResponse(url="/dashboard/reminders", status_code=303)

    @router.get("/pending-operations", response_class=HTMLResponse)
    def pending_operations_page(
        request: Request,
        db: Session = Depends(get_db),
    ) -> HTMLResponse:
        operations = (
            db.query(PendingOperation)
            .filter(PendingOperation.status == PendingOperationStatus.PENDING.value)
            .order_by(PendingOperation.created_at.desc())
            .all()
        )
        recent_operations = (
            db.query(PendingOperation)
            .filter(
                PendingOperation.status.in_(
                    [
                        PendingOperationStatus.APPLIED.value,
                        PendingOperationStatus.REJECTED.value,
                        PendingOperationStatus.FAILED.value,
                    ]
                )
            )
            .order_by(PendingOperation.created_at.desc())
            .limit(50)
            .all()
        )
        return templates.TemplateResponse(
            request,
            "pending_operations.html",
            {
                "active_page": "pending_operations",
                "operations": operations,
                "recent_operations": recent_operations,
                "message": None,
            },
        )

    @router.post("/pending-operations/{operation_id}/confirm")
    def confirm_pending_operation(
        operation_id: int,
        db: Session = Depends(get_db),
    ) -> RedirectResponse:
        executor = ActionExecutor(db)
        try:
            executor.confirm_and_apply(operation_id)
        except ValueError:
            pass
        return RedirectResponse(url="/dashboard/pending-operations", status_code=303)

    @router.post("/pending-operations/{operation_id}/reject")
    def reject_pending_operation(
        operation_id: int,
        db: Session = Depends(get_db),
    ) -> RedirectResponse:
        executor = ActionExecutor(db)
        try:
            executor.reject(operation_id)
        except ValueError:
            pass
        return RedirectResponse(url="/dashboard/pending-operations", status_code=303)

    @router.post("/pending-operations/{operation_id}/update")
    def update_pending_operation_raw_text(
        operation_id: int,
        raw_text: str = Form(...),
        db: Session = Depends(get_db),
    ) -> RedirectResponse:
        pending = db.get(PendingOperation, operation_id)
        if pending and pending.status == PendingOperationStatus.PENDING.value:
            parser = RuleBasedOperationParser(tz=DEFAULT_TZ)
            try:
                parsed = parser.parse(raw_text.strip(), source=pending.source)
            except ValueError:
                return RedirectResponse(url="/dashboard/pending-operations", status_code=303)
            pending.raw_text = parsed.raw_text
            pending.action_name = parsed.action_name
            pending.operation_payload = parsed.payload
            pending.confidence = parsed.confidence
            pending.needs_confirmation = parsed.needs_confirmation
            pending.status = PendingOperationStatus.PENDING.value
            db.commit()
        return RedirectResponse(url="/dashboard/pending-operations", status_code=303)

    @router.get("/logs", response_class=HTMLResponse)
    def logs_page(
        request: Request,
        db: Session = Depends(get_db),
    ) -> HTMLResponse:
        message_logs = (
            db.query(MessageLog)
            .order_by(MessageLog.created_at.desc())
            .limit(100)
            .all()
        )
        recent_operations = (
            db.query(PendingOperation)
            .filter(
                PendingOperation.status.in_(
                    [
                        PendingOperationStatus.APPLIED.value,
                        PendingOperationStatus.REJECTED.value,
                        PendingOperationStatus.FAILED.value,
                    ]
                )
            )
            .order_by(PendingOperation.created_at.desc())
            .limit(50)
            .all()
        )
        return templates.TemplateResponse(
            request,
            "logs.html",
            {
                "active_page": "logs",
                "message_logs": message_logs,
                "recent_operations": recent_operations,
            },
        )

    return router


def mount_web_static(app) -> None:
    app.mount(
        "/dashboard/static",
        StaticFiles(directory=str(WEB_DIR / "static")),
        name="web-static",
    )
