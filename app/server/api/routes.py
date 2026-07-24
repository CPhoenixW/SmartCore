from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.agent.scope import issue_agent_scope
from app.server.auth.security import require_authenticated_user_id
from app.server.config import Settings, get_settings
from app.server.db.session import get_db
from app.server.new_core import crud
from app.server.new_core.ddl_service import (
    create_ddl_event,
    replace_ddl_plans,
    replace_ddl_reminders,
)
from app.server.new_core.event_relations import (
    cancel_event,
    create_course_event,
    create_plan_event,
    ensure_all_relations,
    get_event,
    list_course_events,
    list_events,
    sync_course_plans,
    update_event,
)
from app.server.new_core.models import (
    ActLog,
    DeviceStateLog,
    EvtBase,
    Idea,
    IdeaMediaJob,
    IdeaUpload,
    MsgLog,
    NotifyLog,
    nowIso,
)
from app.server.new_core.preferences import get_user_preferences, update_user_preferences
from app.server.new_core.reminder_service import (
    create_reminder_event,
    get_reminder_event,
    list_reminder_events,
    update_reminder_event,
)

router = APIRouter(prefix="/api", tags=["api"])


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _http_error(exc: ValueError) -> HTTPException:
    msg = str(exc)
    bad_request_terms = (
        "required",
        "disabled",
        "must be",
        "unsupported",
        "duplicate",
        "invalid",
        "earlier",
        "later",
        "cannot be edited",
    )
    if any(term in msg for term in bad_request_terms):
        return HTTPException(status_code=400, detail=msg)
    return HTTPException(status_code=404, detail=msg)


def _row_dict(row: Any) -> dict[str, Any]:
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
    }


def _latest_rows(
    db: Session,
    model: Any,
    order_field: Any,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(model).order_by(order_field.desc()).limit(limit)
    ).all()
    return [_row_dict(row) for row in rows]


class UserPatchBody(BaseModel):
    displayName: str | None = None
    language: str | None = None
    avatarUrl: str | None = None
    reminderChannel: Literal["screen", "feishu"] | None = None


@router.get("/user/me")
def get_user_me(userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = crud.getCurrentUser(db, userId=userId)
    user.update(get_user_preferences(db, user_id=userId))
    db.commit()
    return ok(user)


@router.patch("/user/me")
def patch_user_me(
    body: UserPatchBody,
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        user_fields = body.model_dump(exclude={"reminderChannel"})
        user = crud.updateCurrentUser(db, userId=userId, **user_fields)
        preferences = update_user_preferences(
            db,
            reminder_channel=body.reminderChannel,
            user_id=userId,
        )
        user.update(preferences)
        return ok(user)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/evt")
def list_evt(
    date: str | None = None,
    evtType: list[str] | None = Query(default=None),
    stat: list[str] | None = Query(default=None),
    text: str | None = None,
    includeReminders: bool = False,
    includeCourseTemplates: bool | None = None,
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    include_templates = date is None if includeCourseTemplates is None else includeCourseTemplates
    try:
        rows = list_events(
            db,
            user_id=userId,
            date_value=date,
            evt_types=evtType,
            stats=stat,
            text=text,
            include_reminders=False,
            include_course_templates=include_templates,
        )
        if includeReminders and (not evtType or "remind" in evtType):
            rows.extend(
                list_reminder_events(
                    db,
                    user_id=userId,
                    date_value=date,
                    stats=stat,
                    text=text,
                )
            )
        return ok(rows)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/evt/{evtId}")
def read_evt(
    evtId: str,
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        base = db.get(EvtBase, evtId)
        if base is None or base.userId != userId:
            raise ValueError(f"evt not found: {evtId}")
        return ok(get_reminder_event(db, evtId) if base.evtType == "remind" else get_event(db, evtId))
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.patch("/evt/{evtId}")
def patch_evt(
    evtId: str,
    body: dict[str, Any],
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        base = db.get(EvtBase, evtId)
        if base is None or base.userId != userId:
            raise ValueError(f"evt not found: {evtId}")
        if base.evtType == "remind":
            return ok(update_reminder_event(db, evtId, src="api", **body))
        plans = body.pop("plans", None)
        ddl_reminders = body.pop("ddlReminders", None)
        result = update_event(db, evtId, src="api", **body)
        if base.evtType == "ddl" and plans is not None:
            result = replace_ddl_plans(db, evtId, plans, src="api")
        if base.evtType == "ddl" and ddl_reminders is not None:
            result = replace_ddl_reminders(db, evtId, ddl_reminders, src="api")
        return ok(result)
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.delete("/evt/{evtId}")
def delete_evt(evtId: str, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        base = db.get(EvtBase, evtId)
        if base is None or base.userId != userId:
            raise ValueError(f"evt not found: {evtId}")
        return ok(cancel_event(db, evtId, src="api"))
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


class PlanEvtBody(BaseModel):
    title: str
    stTime: str
    durationMin: int = Field(default=30, gt=0)
    desc: str | None = None
    prio: str = "mid"


@router.get("/planEvt")
def list_plan_evt(
    date: str | None = None,
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(
        list_events(
            db,
            user_id=userId,
            date_value=date,
            evt_types=["plan"],
            include_course_templates=False,
        )
    )


@router.post("/planEvt")
def create_plan_evt(body: PlanEvtBody, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(create_plan_event(db, **body.model_dump(), userId=userId, src="api"))
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


class RemindEvtBody(BaseModel):
    title: str
    triggerTime: str
    desc: str | None = None
    prio: str = "mid"


@router.get("/remindEvt")
def list_remind_evt(
    date: str | None = None,
    stat: list[str] | None = Query(default=None),
    text: str | None = None,
    userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(list_reminder_events(db, user_id=userId, date_value=date, stats=stat, text=text))


@router.post("/remindEvt")
def create_remind_evt(body: RemindEvtBody, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(create_reminder_event(db, **body.model_dump(), userId=userId, src="api"))
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


class DdlPlanBody(BaseModel):
    planEvtId: str | None = None
    planRole: Literal["one_day_before", "one_hour_before", "manual"] = "manual"
    stTime: str
    durationMin: int = Field(default=30, gt=0)
    title: str | None = None
    desc: str | None = None
    enabled: bool = True
    sortOrder: int | None = None


class DdlReminderBody(BaseModel):
    remindEvtId: str | None = None
    triggerTime: str
    title: str | None = None
    desc: str | None = None
    prio: Literal["low", "mid", "high"] = "high"
    enabled: bool = True


class DdlEvtBody(BaseModel):
    title: str
    endTime: str
    hardDdl: bool = False
    desc: str | None = None
    prio: str = "high"
    plans: list[DdlPlanBody] | None = None
    ddlReminders: list[DdlReminderBody] | None = None


@router.get("/ddlEvt")
def list_ddl_evt(userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(list_events(db, user_id=userId, evt_types=["ddl"], include_course_templates=False))


@router.post("/ddlEvt")
def create_ddl_evt(body: DdlEvtBody, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        payload = body.model_dump()
        payload["plans"] = (
            [plan.model_dump(exclude_none=True) for plan in body.plans]
            if body.plans is not None
            else None
        )
        payload["ddlReminders"] = (
            [item.model_dump(exclude_none=True) for item in body.ddlReminders]
            if body.ddlReminders is not None
            else None
        )
        return ok(create_ddl_event(db, **payload, userId=userId, src="api"))
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


class CourseEvtBody(BaseModel):
    title: str | None = None
    courseName: str
    teacher: str | None = None
    location: str | None = None
    stTime: str
    endTime: str
    stDate: str
    endDate: str
    weekDay: int | str
    startWeek: int | None = None
    endWeek: int | None = None
    weekMode: Literal["all", "odd", "even"] = "all"
    desc: str | None = None
    prio: str = "mid"


@router.get("/courseEvt")
def list_course_evt(userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(list_course_events(db, user_id=userId))


@router.post("/courseEvt")
def create_course_evt(body: CourseEvtBody, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(create_course_event(db, **body.model_dump(), userId=userId, src="api"))
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/courseEvt/{evtId}/sync")
def sync_course_occurrences(evtId: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        plans = sync_course_plans(db, evtId)
        db.commit()
        return ok({"course": get_event(db, evtId), "plans": plans})
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/evt/relations/sync")
def sync_all_event_relations(db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ok(ensure_all_relations(db))
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc


class IdeaBody(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    srcType: str = "text"
    uploadIds: list[str] = Field(default_factory=list)


class IdeaPatchBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    handled: bool | None = None
    expectedRevision: int | None = Field(default=None, ge=1)
    addUploadIds: list[str] = Field(default_factory=list, max_length=10)
    removeAttachmentIds: list[str] = Field(default_factory=list, max_length=10)


class IdeaMediaProcessBody(BaseModel):
    uploadIds: list[str] = Field(min_length=1, max_length=10)
    text: str = Field(default="", max_length=4000)


class IdeaMediaJobBody(BaseModel):
    ideaId: str
    uploadId: str
    contextText: str = Field(default="", max_length=4000)


@router.get("/idea")
def list_idea(userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(crud.listIdeas(db, userId=userId))


@router.post("/idea")
def create_idea(body: IdeaBody, userId: str = Depends(require_authenticated_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    upload_ids = list(dict.fromkeys(item.strip() for item in body.uploadIds if item.strip()))
    if upload_ids:
        uploads = db.scalars(
            select(IdeaUpload).where(
                IdeaUpload.uploadId.in_(upload_ids), IdeaUpload.userId == userId
            )
        ).all()
        if len(uploads) != len(upload_ids):
            raise HTTPException(status_code=404, detail="one or more attachments are unavailable")
        if any(upload.mimeType.startswith("image/") for upload in uploads):
            raise HTTPException(
                status_code=409,
                detail="image attachments must use /api/idea/media-process so OCR cannot be skipped",
            )
    return ok(
        crud.createIdea(
            db,
            title=body.title,
            description=body.description,
            srcType=body.srcType,
            uploadIds=upload_ids,
            userId=userId,
        )
    )


@router.post("/idea/media-process")
def process_idea_media(
    body: IdeaMediaProcessBody,
    userId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    upload_ids = list(dict.fromkeys(item.strip() for item in body.uploadIds if item.strip()))
    uploads = db.scalars(
        select(IdeaUpload).where(IdeaUpload.uploadId.in_(upload_ids), IdeaUpload.userId == userId)
    ).all()
    if len(uploads) != len(upload_ids):
        raise HTTPException(status_code=404, detail="one or more attachments are unavailable")
    if not settings.openclaw_events_endpoint or not settings.openclaw_events_token:
        raise HTTPException(status_code=503, detail="media processing is unavailable")
    attachments = [
        {
            "uploadId": row.uploadId,
            "fileName": row.fileName,
            "mimeType": row.mimeType,
            "sizeBytes": row.sizeBytes,
            "agentPath": f"/attachments/{Path(row.storagePath).name}",
        }
        for row in uploads
    ]
    event = {
        "event_id": f"web-media-{nowIso()}",
        "source": "web",
        "event_type": "idea_media",
        "userId": userId,
        "text": body.text.strip(),
        "message": {"text": body.text.strip(), "attachments": attachments},
        "attachments": attachments,
        "agentScope": issue_agent_scope(userId=userId, purpose="web", ttl_seconds=900),
    }
    try:
        response = httpx.post(
            settings.openclaw_events_endpoint,
            json=event,
            headers={"Authorization": f"Bearer {settings.openclaw_events_token}"},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="media processing queue is unavailable") from exc
    return ok({"queued": True, "uploadIds": upload_ids})


@router.post("/idea/media-jobs", status_code=202)
def create_idea_media_job(
    body: IdeaMediaJobBody,
    userId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    idea = db.get(Idea, body.ideaId)
    if idea is None or idea.userId != userId:
        raise HTTPException(status_code=404, detail="idea not found")
    upload = db.get(IdeaUpload, body.uploadId)
    if upload is None or upload.userId != userId:
        raise HTTPException(status_code=404, detail="upload not found")
    if not upload.mimeType.startswith("image/"):
        raise HTTPException(status_code=400, detail="only image uploads require media jobs")
    existing = db.scalar(
        select(IdeaMediaJob).where(
            IdeaMediaJob.uploadId == upload.uploadId,
            IdeaMediaJob.userId == userId,
        )
    )
    if existing is not None:
        if existing.ideaId != idea.ideaId:
            raise HTTPException(status_code=409, detail="upload already belongs to another media job")
        return ok(_media_job_dict(existing))
    if not settings.openclaw_events_endpoint or not settings.openclaw_events_token:
        raise HTTPException(status_code=503, detail="media processing is unavailable")

    now = datetime.now().astimezone()
    job = IdeaMediaJob(
        userId=userId,
        ideaId=idea.ideaId,
        uploadId=upload.uploadId,
        stat="queued",
        contextText=body.contextText.strip(),
        expiresAt=(now + timedelta(hours=24)).isoformat(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        _dispatch_idea_media_job(job, upload, settings=settings)
    except httpx.HTTPError as exc:
        job.stat = "failed"
        job.errorMessage = "media processing queue is unavailable"
        job.updatedAt = nowIso()
        db.commit()
        raise HTTPException(status_code=503, detail=job.errorMessage) from exc
    return ok(_media_job_dict(job))


def _dispatch_idea_media_job(
    job: IdeaMediaJob,
    upload: IdeaUpload,
    *,
    settings: Settings,
) -> None:
    attachment = {
        "uploadId": upload.uploadId,
        "fileName": upload.fileName,
        "mimeType": upload.mimeType,
        "sizeBytes": upload.sizeBytes,
        "agentPath": f"/attachments/{Path(upload.storagePath).name}",
    }
    event = {
        "event_id": f"idea-media-job:{job.jobId}",
        "source": "web",
        "event_type": "idea_media_edit",
        "userId": job.userId,
        "jobId": job.jobId,
        "targetIdeaId": job.ideaId,
        "text": job.contextText,
        "message": {"text": job.contextText, "attachments": [attachment]},
        "attachments": [attachment],
        "agentScope": issue_agent_scope(userId=job.userId, purpose="web", ttl_seconds=900),
    }
    response = httpx.post(
        settings.openclaw_events_endpoint,
        json=event,
        headers={"Authorization": f"Bearer {settings.openclaw_events_token}"},
        timeout=10.0,
    )
    response.raise_for_status()


def _media_job_dict(job: IdeaMediaJob) -> dict[str, Any]:
    return {
        "jobId": job.jobId,
        "ideaId": job.ideaId,
        "uploadId": job.uploadId,
        "stat": job.stat,
        "summary": job.summary,
        "errorMessage": job.errorMessage,
        "createdAt": job.createdAt,
        "updatedAt": job.updatedAt,
    }


@router.get("/idea/media-jobs/{jobId}")
def get_idea_media_job(
    jobId: str,
    userId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    job = db.get(IdeaMediaJob, jobId)
    if job is None or job.userId != userId:
        raise HTTPException(status_code=404, detail="media job not found")
    return ok(_media_job_dict(job))


@router.post("/idea/media-jobs/{jobId}/retry", status_code=202)
def retry_idea_media_job(
    jobId: str,
    userId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    job = db.get(IdeaMediaJob, jobId)
    if job is None or job.userId != userId:
        raise HTTPException(status_code=404, detail="media job not found")
    if job.stat != "failed":
        raise HTTPException(status_code=409, detail="only failed media jobs can be retried")
    upload = db.get(IdeaUpload, job.uploadId)
    if upload is None or upload.userId != userId:
        raise HTTPException(status_code=404, detail="upload not found")
    job.stat = "queued"
    job.ocrText = None
    job.summary = None
    job.ocrEvidence = None
    job.errorMessage = None
    job.updatedAt = nowIso()
    db.commit()
    try:
        _dispatch_idea_media_job(job, upload, settings=settings)
    except httpx.HTTPError as exc:
        job.stat = "failed"
        job.errorMessage = "media processing queue is unavailable"
        job.updatedAt = nowIso()
        db.commit()
        raise HTTPException(status_code=503, detail=job.errorMessage) from exc
    return ok(_media_job_dict(job))


@router.patch("/idea/{ideaId}")
def patch_idea(
    ideaId: str,
    body: IdeaPatchBody,
    userId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return ok(
            crud.updateIdea(
                db,
                ideaId,
                userId=userId,
                title=body.title,
                description=body.description,
                handled=body.handled,
                expectedRevision=body.expectedRevision,
                addUploadIds=body.addUploadIds,
                removeAttachmentIds=body.removeAttachmentIds,
            )
        )
    except ValueError as exc:
        if str(exc) in {"stale idea revision", "image media job is not ready"}:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise _http_error(exc) from exc


@router.delete("/idea/{ideaId}")
def delete_idea(
    ideaId: str,
    userId: str = Depends(require_authenticated_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return ok(crud.deleteIdea(db, ideaId, userId=userId))
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/devState")
def list_dev_state(
    devId: str | None = None,
    limit: int = Query(default=240, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    query = select(DeviceStateLog)
    if devId:
        query = query.where(DeviceStateLog.deviceId == devId)
    rows = db.scalars(
        query.order_by(DeviceStateLog.seenAt.desc()).limit(limit)
    ).all()
    return ok([_row_dict(row) for row in rows])


@router.get("/log")
def list_logs(
    limit: int = Query(default=120, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(
        {
            "act": _latest_rows(db, ActLog, ActLog.createdAt, limit=limit),
            "notify": _latest_rows(db, NotifyLog, NotifyLog.scheduledAt, limit=limit),
            "msg": _latest_rows(db, MsgLog, MsgLog.createdAt, limit=limit),
        }
    )


@router.get("/log/act")
def list_log_act(
    limit: int = Query(default=120, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(_latest_rows(db, ActLog, ActLog.createdAt, limit=limit))


@router.get("/log/notify")
def list_log_notify(
    limit: int = Query(default=120, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(_latest_rows(db, NotifyLog, NotifyLog.scheduledAt, limit=limit))


@router.get("/log/msg")
def list_log_msg(
    limit: int = Query(default=120, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ok(_latest_rows(db, MsgLog, MsgLog.createdAt, limit=limit))


class ReminderActionBody(BaseModel):
    evtId: str
    action: str
    now: str | None = None


@router.post("/reminder/action")
def reminder_action(
    body: ReminderActionBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.server.new_core.event_relations import apply_reminder_action

    try:
        return ok(
            apply_reminder_action(
                db,
                evt_id=body.evtId,
                action=body.action,
                now=body.now or nowIso(),
                src="screen",
            )
        )
    except ValueError as exc:
        db.rollback()
        raise _http_error(exc) from exc
