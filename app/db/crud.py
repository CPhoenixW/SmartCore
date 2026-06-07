from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    AssignmentStatus,
    Course,
    CourseSession,
    LifeEvent,
    LifeEventStatus,
    MessageLog,
    Reminder,
    ReminderStatus,
    WeekRule,
)


def create_course(
    db: Session,
    *,
    name: str,
    teacher: str | None = None,
    default_location: str | None = None,
    notes: str | None = None,
) -> Course:
    course = Course(
        name=name,
        teacher=teacher,
        default_location=default_location,
        notes=notes,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def create_course_session(
    db: Session,
    *,
    course_id: int,
    weekday: int,
    start_period: int | None = None,
    end_period: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    week_rule: WeekRule = WeekRule.EVERY,
    week_range: str | None = None,
    location_override: str | None = None,
) -> CourseSession:
    session = CourseSession(
        course_id=course_id,
        weekday=weekday,
        start_period=start_period,
        end_period=end_period,
        start_time=start_time,
        end_time=end_time,
        week_rule=week_rule.value,
        week_range=week_range,
        location_override=location_override,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def create_assignment(
    db: Session,
    *,
    title: str,
    course_id: int | None = None,
    due_at: datetime | None = None,
    status: AssignmentStatus = AssignmentStatus.PENDING,
    priority: int = 0,
    notes: str | None = None,
) -> Assignment:
    assignment = Assignment(
        title=title,
        course_id=course_id,
        due_at=due_at,
        status=status.value,
        priority=priority,
        notes=notes,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


def create_life_event(
    db: Session,
    *,
    title: str,
    scheduled_at: datetime | None = None,
    deadline_at: datetime | None = None,
    status: LifeEventStatus = LifeEventStatus.PENDING,
    reminder_rule: str | None = None,
    notes: str | None = None,
) -> LifeEvent:
    event = LifeEvent(
        title=title,
        scheduled_at=scheduled_at,
        deadline_at=deadline_at,
        status=status.value,
        reminder_rule=reminder_rule,
        notes=notes,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def create_reminder(
    db: Session,
    *,
    reminder_type: str,
    target_type: str,
    scheduled_at: datetime,
    target_id: int | None = None,
    status: ReminderStatus = ReminderStatus.PENDING,
    content: str | None = None,
) -> Reminder:
    reminder = Reminder(
        reminder_type=reminder_type,
        target_type=target_type,
        target_id=target_id,
        scheduled_at=scheduled_at,
        status=status.value,
        content=content,
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


def create_message_log(
    db: Session,
    *,
    source: str,
    external_message_id: str | None = None,
    raw_content: str | None = None,
    parsed_command: str | None = None,
    reply_status: str | None = None,
    action_input: dict | None = None,
    db_result: dict | None = None,
) -> MessageLog:
    log = MessageLog(
        source=source,
        external_message_id=external_message_id,
        raw_content=raw_content,
        parsed_command=parsed_command,
        reply_status=reply_status,
        action_input=action_input,
        db_result=db_result,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
