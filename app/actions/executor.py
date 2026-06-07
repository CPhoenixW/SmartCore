from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.actions.protocol import (
    PUBLIC_EVENT_TYPES,
    default_end_at,
    default_reminder_times,
    format_time_label,
    make_result,
    map_legacy_event_type,
    map_status_filter,
    normalize_datetime,
    parse_iso_datetime,
    read_sc_type,
    sc_type_tag,
)
from app.db import crud
from app.db.models import (
    Assignment,
    AssignmentStatus,
    Course,
    CourseSession,
    LifeEvent,
    LifeEventStatus,
    PendingOperation,
    PendingOperationStatus,
    Reminder,
    ReminderStatus,
)
from app.operations.parser import ParsedOperation
from app.operations.store import create_pending_operation
from app.secretary.rules import DEFAULT_TZ


class ActionExecutor:
    def __init__(self, db: Session) -> None:
        self._db = db

    def execute(self, action: dict[str, Any]) -> dict[str, Any]:
        action_name = action.get("action")
        handlers = {
            "create_event": self._execute_create_event,
            "query_event": self._execute_query_event,
            "update_event": self._execute_update_event,
            "delete_event": self._execute_delete_event,
        }
        handler = handlers.get(action_name)
        if handler is None:
            return make_result(
                action=str(action_name or ""),
                status="failed",
                ok=False,
                message_code="UNSUPPORTED_ACTION",
                errors=[f"unsupported action: {action_name!r}"],
                model_input=action,
                db_result={"status": "failed"},
            )
        return handler(action)

    def confirm_and_apply_result(self, operation_id: int) -> dict[str, Any]:
        pending = self.confirm_and_apply(operation_id)
        action_name = pending.action_name
        if pending.status == PendingOperationStatus.APPLIED.value:
            data = self._build_applied_result_data(pending)
            return make_result(
                action=action_name,
                status="applied",
                message_code="EVENT_APPLIED",
                operation_id=operation_id,
                data=data,
                model_input=pending.operation_payload,
                db_result={"status": "applied", "resource_type": pending.result_resource_type},
            )
        if pending.status == PendingOperationStatus.FAILED.value:
            return make_result(
                action=action_name,
                status="failed",
                ok=False,
                message_code="EVENT_APPLY_FAILED",
                operation_id=operation_id,
                errors=[pending.error_message or "apply failed"],
                model_input=pending.operation_payload,
                db_result={"status": "failed"},
            )
        return make_result(
            action=action_name,
            status="failed",
            ok=False,
            message_code="EVENT_APPLY_FAILED",
            operation_id=operation_id,
            errors=[f"unexpected pending status: {pending.status}"],
            model_input=pending.operation_payload,
            db_result={"status": pending.status},
        )

    def confirm_and_apply(self, operation_id: int) -> PendingOperation:
        pending = self._get_pending_operation(operation_id)
        handlers = {
            "create_event": self._apply_create_event,
            "update_event": self._apply_update_event,
            "delete_event": self._apply_delete_event,
        }
        handler = handlers.get(pending.action_name)
        if handler is None:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = f"unsupported action: {pending.action_name}"
            self._db.commit()
            self._db.refresh(pending)
            return pending
        try:
            return handler(pending)
        except Exception as exc:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = str(exc)
            self._db.commit()
            self._db.refresh(pending)
            return pending

    def reject(self, operation_id: int) -> PendingOperation:
        pending = self._get_pending_operation(operation_id)
        pending.status = PendingOperationStatus.REJECTED.value
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _get_pending_operation(self, operation_id: int) -> PendingOperation:
        pending = self._db.get(PendingOperation, operation_id)
        if pending is None:
            raise ValueError(f"pending operation not found: {operation_id}")
        if pending.status != PendingOperationStatus.PENDING.value:
            raise ValueError(f"operation {operation_id} is not pending")
        return pending

    def _execute_create_event(self, action: dict[str, Any]) -> dict[str, Any]:
        event = (action.get("payload") or {}).get("event") or {}
        event_type = event.get("event_type")
        title = event.get("title")
        if event_type not in PUBLIC_EVENT_TYPES:
            return make_result(
                action="create_event",
                status="failed",
                ok=False,
                message_code="INVALID_EVENT_TYPE",
                errors=[f"unsupported event_type: {event_type!r}"],
                model_input=action,
                db_result={"status": "failed"},
            )
        if not title:
            return make_result(
                action="create_event",
                status="failed",
                ok=False,
                message_code="MISSING_TITLE",
                errors=["missing event title"],
                model_input=action,
                db_result={"status": "failed"},
            )
        start_at = parse_iso_datetime(event.get("start_at"))
        if start_at is None and event_type in {"schedule", "deadline"}:
            if not event.get("unscheduled"):
                return make_result(
                    action="create_event",
                    status="failed",
                    ok=False,
                    message_code="MISSING_START_AT",
                    errors=["missing start_at"],
                    model_input=action,
                    db_result={"status": "failed"},
                )
        elif start_at is None:
            return make_result(
                action="create_event",
                status="failed",
                ok=False,
                message_code="MISSING_START_AT",
                errors=["missing start_at"],
                model_input=action,
                db_result={"status": "failed"},
            )
        end_at = parse_iso_datetime(event.get("end_at"))
        if end_at is None:
            end_at = default_end_at(start_at, event_type)
        preview = self._build_event_preview(
            event_type,
            event,
            start_at or datetime.now(DEFAULT_TZ),
            end_at,
        )
        if start_at is None:
            preview.pop("start_at", None)
            preview.pop("reminders", None)
        parsed = ParsedOperation(
            source=action.get("source", "feishu"),
            raw_text=action.get("raw_text", title),
            action_name="create_event",
            payload=action,
            confidence=1.0,
            needs_confirmation=True,
        )
        pending = create_pending_operation(self._db, parsed)
        return make_result(
            action="create_event",
            status="pending_confirmation",
            message_code="EVENT_CREATE_PREVIEW",
            operation_id=pending.id,
            data={"preview": preview},
            model_input=action,
            db_result={"status": "pending_confirmation", "operation_id": pending.id},
        )

    def _execute_query_event(self, action: dict[str, Any]) -> dict[str, Any]:
        payload = action.get("payload") or {}
        filter_payload = payload.get("filter") or {}
        event_type = map_legacy_event_type(filter_payload.get("event_type", "all"))
        status_filter = map_status_filter(filter_payload.get("status"))
        limit = min(int(filter_payload.get("limit") or 20), 50)
        time_range = filter_payload.get("time_range")
        range_start, range_end = self._parse_time_range(time_range)
        internal = self._collect_internal_events(
            event_type=event_type,
            status_filter=status_filter,
            range_start=range_start,
            range_end=range_end,
            limit=limit,
        )
        events, _ = self._assign_candidate_refs(internal)
        return make_result(
            action="query_event",
            status="applied",
            message_code="EVENTS_FOUND",
            data={"events": events},
            model_input=action,
            db_result={"count": len(events), "status": "applied"},
        )

    def _execute_update_event(self, action: dict[str, Any]) -> dict[str, Any]:
        payload = action.get("payload") or {}
        selector = payload.get("selector") or {}
        patch = payload.get("patch") or {}
        resolved = self._resolve_selector(selector)
        if resolved["status"] != "resolved":
            return make_result(
                action="update_event",
                status=resolved["status"],
                ok=resolved["status"] != "failed",
                message_code=resolved.get("message_code", "UPDATE_FAILED"),
                errors=resolved.get("errors", []),
                model_input=action,
                db_result={"status": resolved["status"]},
            )
        update_action = dict(action)
        update_payload: dict[str, Any] = {
            "selector": resolved["selector"],
            "patch": patch,
        }
        if resolved.get("selected_candidates"):
            update_payload["selected_candidates"] = resolved["selected_candidates"]
        update_action["payload"] = update_payload
        parsed = ParsedOperation(
            source=action.get("source", "feishu"),
            raw_text=action.get("raw_text", ""),
            action_name="update_event",
            payload=update_action,
            confidence=1.0,
            needs_confirmation=True,
        )
        pending = create_pending_operation(self._db, parsed)
        return make_result(
            action="update_event",
            status="pending_confirmation",
            message_code="EVENT_UPDATE_PREVIEW",
            operation_id=pending.id,
            data={"preview": resolved.get("preview", {})},
            model_input=action,
            db_result={"status": "pending_confirmation", "operation_id": pending.id},
        )

    def _execute_delete_event(self, action: dict[str, Any]) -> dict[str, Any]:
        payload = action.get("payload") or {}
        selector = payload.get("selector") or {}
        resolved = self._resolve_selector(selector, allow_multiple=True)
        if resolved["status"] != "resolved":
            return make_result(
                action="delete_event",
                status=resolved["status"],
                ok=resolved["status"] != "failed",
                message_code=resolved.get("message_code", "DELETE_FAILED"),
                errors=resolved.get("errors", []),
                model_input=action,
                db_result={"status": resolved["status"]},
            )
        delete_action = dict(action)
        delete_payload: dict[str, Any] = {"selector": resolved["selector"]}
        if resolved.get("selected_candidates"):
            delete_payload["selected_candidates"] = resolved["selected_candidates"]
        delete_action["payload"] = delete_payload
        parsed = ParsedOperation(
            source=action.get("source", "feishu"),
            raw_text=action.get("raw_text", ""),
            action_name="delete_event",
            payload=delete_action,
            confidence=1.0,
            needs_confirmation=True,
        )
        pending = create_pending_operation(self._db, parsed)
        return make_result(
            action="delete_event",
            status="pending_confirmation",
            message_code="EVENT_DELETE_PREVIEW",
            operation_id=pending.id,
            data={"preview": resolved.get("preview", {})},
            model_input=action,
            db_result={"status": "pending_confirmation", "operation_id": pending.id},
        )

    def _build_event_preview(
        self,
        event_type: str,
        event: dict[str, Any],
        start_at: datetime,
        end_at: datetime | None,
    ) -> dict[str, Any]:
        preview: dict[str, Any] = {
            "event_type": event_type,
            "title": event.get("title"),
            "start_at": start_at.isoformat(),
        }
        if event_type in ("plan", "course") and end_at is not None:
            preview["end_at"] = end_at.isoformat()
        if event_type == "course" and event.get("location"):
            preview["location"] = event.get("location")
        if event_type in ("schedule", "deadline"):
            preview["reminders"] = [
                item.isoformat() for item in default_reminder_times(start_at)
            ]
        return preview

    def _build_applied_result_data(self, pending: PendingOperation) -> dict[str, Any]:
        action_payload = pending.operation_payload
        if isinstance(action_payload.get("payload"), dict) and action_payload[
            "payload"
        ].get("event"):
            event_spec = action_payload["payload"]["event"]
            event_type = event_spec.get("event_type")
            resource_type = pending.result_resource_type
            resource_id = pending.result_resource_id
            if resource_type and resource_id is not None:
                return {
                    "event": self._load_public_event(
                        event_type,
                        resource_type,
                        resource_id,
                    )
                }
        return {}

    def _load_public_event(
        self,
        event_type: str | None,
        resource_type: str,
        resource_id: int,
    ) -> dict[str, Any]:
        if resource_type == "assignment":
            item = self._db.get(Assignment, resource_id)
            if item is None:
                return {}
            start_at = normalize_datetime(item.due_at)
            reminders = self._load_reminder_times("assignment", item.id)
            return {
                "event_type": "deadline",
                "title": item.title,
                "start_at": start_at.isoformat() if start_at else None,
                "reminders": reminders,
            }
        if resource_type == "life_event":
            item = self._db.get(LifeEvent, resource_id)
            if item is None:
                return {}
            public_type = read_sc_type(item.reminder_rule) or event_type or "schedule"
            start_at = normalize_datetime(item.scheduled_at)
            end_at = normalize_datetime(item.deadline_at)
            data: dict[str, Any] = {
                "event_type": public_type,
                "title": item.title,
                "start_at": start_at.isoformat() if start_at else None,
            }
            if public_type in ("plan", "course") and end_at is not None:
                data["end_at"] = end_at.isoformat()
            if public_type == "course" and item.notes:
                data["location"] = item.notes
            if public_type in ("schedule", "deadline"):
                data["reminders"] = self._load_reminder_times("life_event", item.id)
            return data
        if resource_type == "course_session":
            item = self._db.get(CourseSession, resource_id)
            if item is None:
                return {}
            title = item.course.name if item.course else ""
            return {
                "event_type": "course",
                "title": title,
                "start_at": None,
                "end_at": None,
                "location": item.location_override,
            }
        return {}

    def _load_reminder_times(self, target_type: str, target_id: int) -> list[str]:
        reminders = (
            self._db.query(Reminder)
            .filter(
                Reminder.target_type == target_type,
                Reminder.target_id == target_id,
                Reminder.status.in_(
                    [ReminderStatus.PENDING.value, ReminderStatus.SENT.value]
                ),
            )
            .order_by(Reminder.scheduled_at.asc())
            .all()
        )
        return [
            normalize_datetime(item.scheduled_at).isoformat()
            for item in reminders
            if item.scheduled_at is not None
        ]

    def _collect_internal_events(
        self,
        *,
        event_type: str,
        status_filter: set[str] | None,
        range_start: datetime | None,
        range_end: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        allowed_status = status_filter or {"pending", "active"}

        if event_type in ("all", "deadline"):
            query = self._db.query(Assignment)
            if "pending" in allowed_status and "active" not in allowed_status:
                query = query.filter(Assignment.status == AssignmentStatus.PENDING.value)
            elif allowed_status == {"pending", "active"}:
                query = query.filter(
                    Assignment.status.notin_(
                        [AssignmentStatus.DONE.value, AssignmentStatus.CANCELLED.value]
                    )
                )
            for item in query.all():
                due_at = normalize_datetime(item.due_at)
                if range_start is not None or range_end is not None:
                    if not self._datetime_in_range(due_at, range_start, range_end):
                        continue
                results.append(
                    {
                        "_storage_type": "assignment",
                        "_id": item.id,
                        "event_type": "deadline",
                        "title": item.title,
                        "status": item.status,
                        "start_at": due_at.isoformat() if due_at else None,
                        "end_at": None,
                        "time_label": format_time_label(due_at),
                    }
                )

        if event_type in ("all", "plan", "schedule", "course"):
            query = self._db.query(LifeEvent)
            if allowed_status == {"pending", "active"}:
                query = query.filter(
                    LifeEvent.status.notin_(
                        [LifeEventStatus.DONE.value, LifeEventStatus.CANCELLED.value]
                    )
                )
            for item in query.all():
                public_type = read_sc_type(item.reminder_rule) or "schedule"
                if event_type != "all" and public_type != event_type:
                    continue
                start_at = normalize_datetime(item.scheduled_at)
                end_at = normalize_datetime(item.deadline_at)
                if range_start is not None or range_end is not None:
                    if not self._life_event_in_time_range(item, range_start, range_end):
                        continue
                results.append(
                    {
                        "_storage_type": "life_event",
                        "_id": item.id,
                        "event_type": public_type,
                        "title": item.title,
                        "status": item.status,
                        "start_at": start_at.isoformat() if start_at else None,
                        "end_at": end_at.isoformat() if end_at else None,
                        "time_label": format_time_label(start_at, end_at),
                    }
                )

        if event_type in ("all", "course"):
            for item in self._db.query(CourseSession).all():
                title = item.course.name if item.course else ""
                results.append(
                    {
                        "_storage_type": "course_session",
                        "_id": item.id,
                        "event_type": "course",
                        "title": title,
                        "status": "active",
                        "start_at": None,
                        "end_at": None,
                        "time_label": "",
                    }
                )

        return results[:limit]

    def _assign_candidate_refs(
        self,
        internal: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, tuple[str, int]]]:
        sorted_items = sorted(
            internal, key=lambda item: (item["_storage_type"], item["_id"])
        )
        public_items: list[dict[str, Any]] = []
        ref_index: dict[str, tuple[str, int]] = {}
        for index, item in enumerate(sorted_items, start=1):
            ref = f"c{index}"
            ref_index[ref] = (item["_storage_type"], item["_id"])
            public_items.append(
                {
                    "ref": ref,
                    "event_type": item["event_type"],
                    "title": item["title"],
                    "status": item["status"],
                    "start_at": item.get("start_at"),
                    "end_at": item.get("end_at"),
                    "time_label": item.get("time_label", ""),
                }
            )
        return public_items, ref_index

    def _build_ref_index_from_selector(
        self,
        selector: dict[str, Any],
    ) -> dict[str, tuple[str, int]]:
        filter_payload = selector.get("filter") or {}
        event_type = map_legacy_event_type(filter_payload.get("event_type", "all"))
        time_range = filter_payload.get("time_range")
        range_start, range_end = self._parse_time_range(time_range)
        internal = self._collect_internal_events(
            event_type=event_type,
            status_filter=map_status_filter(filter_payload.get("status")),
            range_start=range_start,
            range_end=range_end,
            limit=selector.get("limit") or filter_payload.get("limit") or 50,
        )
        _, ref_index = self._assign_candidate_refs(internal)
        return ref_index

    def _resolve_selector(
        self,
        selector: dict[str, Any],
        *,
        allow_multiple: bool = False,
    ) -> dict[str, Any]:
        mode = selector.get("mode")
        if mode == "legacy_id":
            return {
                "status": "resolved",
                "selector": {
                    "event_type": selector.get("event_type"),
                    "id": selector.get("id"),
                },
            }
        if mode == "legacy_targets":
            return {
                "status": "resolved",
                "selector": {"targets": selector.get("targets") or []},
            }
        if selector.get("id") is not None and not mode:
            return {
                "status": "resolved",
                "selector": {
                    "event_type": selector.get("event_type"),
                    "id": selector.get("id"),
                },
            }
        if selector.get("targets"):
            return {
                "status": "resolved",
                "selector": {"targets": selector.get("targets")},
            }

        refs = selector.get("refs") or []
        ref_index = self._build_ref_index_from_selector(selector)
        public_candidates, _ = self._assign_candidate_refs(
            self._collect_internal_events(
                event_type=map_legacy_event_type(
                    (selector.get("filter") or {}).get("event_type", "all")
                ),
                status_filter=map_status_filter(
                    (selector.get("filter") or {}).get("status")
                ),
                range_start=self._parse_time_range(
                    (selector.get("filter") or {}).get("time_range")
                )[0],
                range_end=self._parse_time_range(
                    (selector.get("filter") or {}).get("time_range")
                )[1],
                limit=(selector.get("filter") or {}).get("limit") or 50,
            )
        )
        ref_map = {item["ref"]: item for item in public_candidates}
        if not refs:
            return {
                "status": "ambiguous",
                "message_code": "MISSING_REFS",
                "errors": ["selector refs are required"],
            }
        missing = [ref for ref in refs if ref not in ref_index]
        if missing:
            return {
                "status": "not_found",
                "message_code": "REF_NOT_FOUND",
                "errors": [f"unknown candidate ref: {missing[0]}"],
            }
        if not allow_multiple and len(refs) != 1:
            return {
                "status": "ambiguous",
                "message_code": "MULTIPLE_REFS",
                "errors": ["update requires exactly one candidate ref"],
            }
        if allow_multiple:
            targets = []
            selected_candidates = []
            for ref in refs:
                storage_type, resource_id = ref_index[ref]
                item = ref_map[ref]
                targets.append(
                    {
                        "event_type": self._legacy_type_from_storage(storage_type),
                        "id": resource_id,
                    }
                )
                selected_candidates.append(
                    {
                        "ref": ref,
                        "title": item.get("title"),
                        "event_type": item.get("event_type"),
                        "time_label": item.get("time_label"),
                    }
                )
            return {
                "status": "resolved",
                "selector": {"targets": targets},
                "preview": {"refs": refs},
                "selected_candidates": selected_candidates,
            }
        ref = refs[0]
        item = ref_map[ref]
        storage_type, resource_id = ref_index[ref]
        return {
            "status": "resolved",
            "selector": {
                "event_type": self._legacy_type_from_storage(storage_type),
                "id": resource_id,
            },
            "preview": {"ref": ref, "title": item.get("title")},
            "selected_candidates": [
                {
                    "ref": ref,
                    "title": item.get("title"),
                    "event_type": item.get("event_type"),
                    "time_label": item.get("time_label"),
                    "id": resource_id,
                }
            ],
        }

    @staticmethod
    def _legacy_type_from_storage(storage_type: str) -> str:
        return {
            "assignment": "assignment",
            "life_event": "life_event",
            "course_session": "course_session",
        }[storage_type]

    def _create_life_event_from_fields(
        self,
        pending: PendingOperation,
        fields: dict,
    ) -> PendingOperation:
        title = fields.get("title")
        if not title:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "missing life event title"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        scheduled_at: datetime | None = None
        raw_scheduled_at = fields.get("scheduled_at")
        if raw_scheduled_at:
            scheduled_at = datetime.fromisoformat(raw_scheduled_at)

        deadline_at: datetime | None = None
        raw_deadline_at = fields.get("deadline_at")
        if raw_deadline_at:
            deadline_at = datetime.fromisoformat(raw_deadline_at)

        reminder_rule = fields.get("reminder_rule")
        notes = fields.get("notes")

        event = crud.create_life_event(
            self._db,
            title=title,
            scheduled_at=scheduled_at,
            deadline_at=deadline_at,
            reminder_rule=reminder_rule if isinstance(reminder_rule, str) else None,
            notes=notes if isinstance(notes, str) else None,
        )
        if scheduled_at is not None:
            lead_minutes = 15
            raw_lead = fields.get("reminder_lead_minutes")
            if raw_lead is not None:
                lead_minutes = int(raw_lead)
            try:
                crud.create_reminder(
                    self._db,
                    reminder_type="life_event_pre_event",
                    target_type="life_event",
                    target_id=event.id,
                    scheduled_at=scheduled_at - timedelta(minutes=lead_minutes),
                    content=f"提醒：{title}",
                )
            except Exception as exc:
                self._db.delete(event)
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = str(exc)
                self._db.commit()
                self._db.refresh(pending)
                return pending
        pending.status = PendingOperationStatus.APPLIED.value
        pending.result_resource_type = "life_event"
        pending.result_resource_id = event.id
        pending.error_message = None
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def query_events(self, payload: dict) -> list[dict]:
        selector = payload.get("selector") or {}
        fields = payload.get("fields") or {}
        event_type = selector.get("event_type") or fields.get("event_type", "all")
        status_filter = selector.get("status") or fields.get("status", "open")
        raw_max = selector.get("max_candidates") or fields.get("max_candidates") or 20
        max_candidates = min(int(raw_max), 50)
        time_range = selector.get("time_range") or fields.get("time_range")
        range_start, range_end = self._parse_time_range(time_range)
        results: list[dict] = []

        if event_type in ("all", "assignment"):
            query = self._db.query(Assignment)
            if status_filter == "open":
                query = query.filter(
                    Assignment.status.notin_(
                        [AssignmentStatus.DONE.value, AssignmentStatus.CANCELLED.value]
                    )
                )
            for item in query.all():
                if range_start is not None or range_end is not None:
                    if not self._datetime_in_range(item.due_at, range_start, range_end):
                        continue
                results.append(self._compact_assignment(item))

        if event_type in ("all", "life_event"):
            query = self._db.query(LifeEvent)
            if status_filter == "open":
                query = query.filter(
                    LifeEvent.status.notin_(
                        [LifeEventStatus.DONE.value, LifeEventStatus.CANCELLED.value]
                    )
                )
            for item in query.all():
                if range_start is not None or range_end is not None:
                    if not self._life_event_in_time_range(
                        item, range_start, range_end
                    ):
                        continue
                results.append(self._compact_life_event(item))

        if event_type in ("all", "course_session"):
            for item in self._db.query(CourseSession).all():
                results.append(self._compact_course_session(item))

        return results[:max_candidates]

    @staticmethod
    def _parse_time_range(
        time_range: dict | None,
    ) -> tuple[datetime | None, datetime | None]:
        if not isinstance(time_range, dict):
            return None, None
        start_raw = time_range.get("start")
        end_raw = time_range.get("end")
        start = datetime.fromisoformat(start_raw) if start_raw else None
        end = datetime.fromisoformat(end_raw) if end_raw else None
        return start, end

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=DEFAULT_TZ)
        return value

    def _datetime_in_range(
        self,
        value: datetime | None,
        range_start: datetime | None,
        range_end: datetime | None,
    ) -> bool:
        dt = self._normalize_datetime(value)
        if dt is None:
            return False
        if range_start is not None:
            start = self._normalize_datetime(range_start)
            if start is not None and dt < start:
                return False
        if range_end is not None:
            end = self._normalize_datetime(range_end)
            if end is not None and dt >= end:
                return False
        return True

    def _life_event_in_time_range(
        self,
        event: LifeEvent,
        range_start: datetime | None,
        range_end: datetime | None,
    ) -> bool:
        for attr in ("scheduled_at", "deadline_at"):
            if self._datetime_in_range(getattr(event, attr), range_start, range_end):
                return True
        return False

    @staticmethod
    def _format_time_label(value: datetime | None) -> str:
        dt = ActionExecutor._normalize_datetime(value)
        if dt is None:
            return ""
        return dt.strftime("%Y-%m-%d %H:%M")

    @classmethod
    def _compact_assignment(cls, item: Assignment) -> dict:
        return {
            "event_type": "assignment",
            "id": item.id,
            "status": item.status,
            "time_label": cls._format_time_label(item.due_at),
            "title": item.title,
        }

    @classmethod
    def _compact_life_event(cls, item: LifeEvent) -> dict:
        time_source = item.scheduled_at or item.deadline_at
        return {
            "event_type": "life_event",
            "id": item.id,
            "status": item.status,
            "time_label": cls._format_time_label(time_source),
            "title": item.title,
        }

    @classmethod
    def _compact_course_session(cls, item: CourseSession) -> dict:
        return {
            "event_type": "course_session",
            "id": item.id,
            "status": "active",
            "time_label": "",
            "title": item.course.name if item.course else "",
        }

    def _apply_create_event(self, pending: PendingOperation) -> PendingOperation:
        payload = pending.operation_payload
        new_event = (payload.get("payload") or {}).get("event")
        if isinstance(new_event, dict):
            return self._apply_new_create_event(pending, new_event)

        fields = payload.get("fields") or {}
        event_type = fields.get("event_type")
        if event_type == "assignment":
            return self._create_event_assignment(pending, fields)
        if event_type == "life_event":
            return self._create_event_life_event(pending, fields)
        if event_type == "course_session":
            return self._create_event_course_session(pending, fields)
        pending.status = PendingOperationStatus.FAILED.value
        pending.error_message = f"unsupported event_type: {event_type}"
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _apply_new_create_event(
        self,
        pending: PendingOperation,
        event: dict[str, Any],
    ) -> PendingOperation:
        event_type = event.get("event_type")
        title = event.get("title")
        if event_type not in PUBLIC_EVENT_TYPES or not title:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "invalid create event payload"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        start_at = parse_iso_datetime(event.get("start_at"))
        end_at = parse_iso_datetime(event.get("end_at"))
        if start_at is not None and end_at is None:
            end_at = default_end_at(start_at, event_type)

        if event_type == "deadline":
            if start_at is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = "missing start_at"
                self._db.commit()
                self._db.refresh(pending)
                return pending
            return self._create_public_deadline(pending, title, start_at, event)
        if event_type == "plan":
            if start_at is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = "missing start_at"
                self._db.commit()
                self._db.refresh(pending)
                return pending
            return self._create_public_plan(pending, title, start_at, end_at, event)
        if event_type == "schedule":
            return self._create_public_schedule(pending, title, start_at, event)
        if event_type == "course":
            return self._create_public_course(pending, title, start_at, end_at, event)

        pending.status = PendingOperationStatus.FAILED.value
        pending.error_message = f"unsupported event_type: {event_type}"
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _create_public_deadline(
        self,
        pending: PendingOperation,
        title: str,
        start_at: datetime,
        event: dict[str, Any],
    ) -> PendingOperation:
        assignment = crud.create_assignment(self._db, title=title, due_at=start_at)
        try:
            self._create_default_reminders(
                target_type="assignment",
                target_id=assignment.id,
                title=title,
                start_at=start_at,
            )
        except Exception as exc:
            self._db.delete(assignment)
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = str(exc)
            self._db.commit()
            self._db.refresh(pending)
            return pending
        pending.status = PendingOperationStatus.APPLIED.value
        pending.result_resource_type = "assignment"
        pending.result_resource_id = assignment.id
        pending.error_message = None
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _create_public_plan(
        self,
        pending: PendingOperation,
        title: str,
        start_at: datetime,
        end_at: datetime | None,
        event: dict[str, Any],
    ) -> PendingOperation:
        life_event = crud.create_life_event(
            self._db,
            title=title,
            scheduled_at=start_at,
            deadline_at=end_at,
            reminder_rule=sc_type_tag("plan"),
            notes=event.get("notes") if isinstance(event.get("notes"), str) else None,
        )
        pending.status = PendingOperationStatus.APPLIED.value
        pending.result_resource_type = "life_event"
        pending.result_resource_id = life_event.id
        pending.error_message = None
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _create_public_schedule(
        self,
        pending: PendingOperation,
        title: str,
        start_at: datetime | None,
        event: dict[str, Any],
    ) -> PendingOperation:
        life_event = crud.create_life_event(
            self._db,
            title=title,
            scheduled_at=start_at,
            reminder_rule=sc_type_tag("schedule"),
            notes=event.get("notes") if isinstance(event.get("notes"), str) else None,
        )
        if start_at is not None:
            try:
                self._create_default_reminders(
                    target_type="life_event",
                    target_id=life_event.id,
                    title=title,
                    start_at=start_at,
                )
            except Exception as exc:
                self._db.delete(life_event)
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = str(exc)
                self._db.commit()
                self._db.refresh(pending)
                return pending
        pending.status = PendingOperationStatus.APPLIED.value
        pending.result_resource_type = "life_event"
        pending.result_resource_id = life_event.id
        pending.error_message = None
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _create_public_course(
        self,
        pending: PendingOperation,
        title: str,
        start_at: datetime,
        end_at: datetime | None,
        event: dict[str, Any],
    ) -> PendingOperation:
        location = event.get("location")
        life_event = crud.create_life_event(
            self._db,
            title=title,
            scheduled_at=start_at,
            deadline_at=end_at,
            reminder_rule=sc_type_tag("course"),
            notes=location if isinstance(location, str) else None,
        )
        pending.status = PendingOperationStatus.APPLIED.value
        pending.result_resource_type = "life_event"
        pending.result_resource_id = life_event.id
        pending.error_message = None
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _create_default_reminders(
        self,
        *,
        target_type: str,
        target_id: int,
        title: str,
        start_at: datetime,
    ) -> None:
        reminder_type = (
            "assignment_pre_due"
            if target_type == "assignment"
            else "life_event_pre_event"
        )
        for scheduled_at in default_reminder_times(start_at):
            crud.create_reminder(
                self._db,
                reminder_type=reminder_type,
                target_type=target_type,
                target_id=target_id,
                scheduled_at=scheduled_at,
                content=f"提醒：{title}",
            )

    def _create_event_assignment(
        self, pending: PendingOperation, fields: dict
    ) -> PendingOperation:
        title = fields.get("title")
        if not title:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "missing assignment title"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        due_at: datetime | None = None
        raw_due_at = fields.get("due_at")
        if raw_due_at:
            due_at = datetime.fromisoformat(raw_due_at)

        assignment = crud.create_assignment(self._db, title=title, due_at=due_at)
        pending.status = PendingOperationStatus.APPLIED.value
        pending.result_resource_type = "assignment"
        pending.result_resource_id = assignment.id
        pending.error_message = None
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _create_event_life_event(
        self, pending: PendingOperation, fields: dict
    ) -> PendingOperation:
        life_fields = {k: v for k, v in fields.items() if k != "event_type"}
        return self._create_life_event_from_fields(pending, life_fields)

    def _create_event_course_session(
        self, pending: PendingOperation, fields: dict
    ) -> PendingOperation:
        course_name = fields.get("course_name")
        if not course_name:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "missing course_name"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        course = self._db.query(Course).filter(Course.name == course_name).first()
        if course is None:
            course = crud.create_course(
                self._db,
                name=course_name,
                teacher=fields.get("teacher") if isinstance(fields.get("teacher"), str) else None,
            )

        weekday = fields.get("weekday")
        if weekday is None:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "missing weekday"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        start_time = fields.get("start_time")
        end_time = fields.get("end_time")
        location = fields.get("location")
        session = crud.create_course_session(
            self._db,
            course_id=course.id,
            weekday=int(weekday),
            start_time=start_time if isinstance(start_time, str) else None,
            end_time=end_time if isinstance(end_time, str) else None,
            location_override=location if isinstance(location, str) else None,
        )
        pending.status = PendingOperationStatus.APPLIED.value
        pending.result_resource_type = "course_session"
        pending.result_resource_id = session.id
        pending.error_message = None
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _apply_update_event(self, pending: PendingOperation) -> PendingOperation:
        payload = pending.operation_payload
        inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        selector = inner.get("selector") or payload.get("selector") or {}
        fields = inner.get("patch") or payload.get("fields") or {}
        event_type = selector.get("event_type") or fields.get("event_type")
        resource_id = selector.get("id")

        if resource_id is None:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "missing event id"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        if event_type == "life_event":
            event = self._db.get(LifeEvent, resource_id)
            if event is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"life_event not found: {resource_id}"
                self._db.commit()
                self._db.refresh(pending)
                return pending

            if "title" in fields:
                event.title = fields["title"]
            start_patch = fields.get("start_at") or fields.get("scheduled_at")
            if start_patch:
                event.scheduled_at = datetime.fromisoformat(start_patch)
                self._reschedule_life_event_reminders(event, fields)
            if fields.get("deadline_at"):
                event.deadline_at = datetime.fromisoformat(fields["deadline_at"])
            if fields.get("end_at"):
                event.deadline_at = datetime.fromisoformat(fields["end_at"])
            if "notes" in fields:
                event.notes = fields["notes"]

            pending.status = PendingOperationStatus.APPLIED.value
            pending.result_resource_type = "life_event"
            pending.result_resource_id = event.id
            pending.error_message = None
            self._db.commit()
            self._db.refresh(pending)
            return pending

        if event_type == "assignment":
            assignment = self._db.get(Assignment, resource_id)
            if assignment is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"assignment not found: {resource_id}"
                self._db.commit()
                self._db.refresh(pending)
                return pending

            if "title" in fields:
                assignment.title = fields["title"]
            due_patch = fields.get("due_at") or fields.get("start_at")
            if due_patch:
                assignment.due_at = datetime.fromisoformat(due_patch)
            if "notes" in fields:
                assignment.notes = fields["notes"]

            pending.status = PendingOperationStatus.APPLIED.value
            pending.result_resource_type = "assignment"
            pending.result_resource_id = assignment.id
            pending.error_message = None
            self._db.commit()
            self._db.refresh(pending)
            return pending

        if event_type == "course_session":
            session = self._db.get(CourseSession, resource_id)
            if session is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"course_session not found: {resource_id}"
                self._db.commit()
                self._db.refresh(pending)
                return pending

            if "weekday" in fields:
                session.weekday = int(fields["weekday"])
            if "start_time" in fields:
                session.start_time = fields["start_time"]
            if "end_time" in fields:
                session.end_time = fields["end_time"]
            if "location" in fields:
                session.location_override = fields["location"]

            pending.status = PendingOperationStatus.APPLIED.value
            pending.result_resource_type = "course_session"
            pending.result_resource_id = session.id
            pending.error_message = None
            self._db.commit()
            self._db.refresh(pending)
            return pending

        pending.status = PendingOperationStatus.FAILED.value
        pending.error_message = f"unsupported event_type for update: {event_type}"
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _reschedule_life_event_reminders(
        self,
        event: LifeEvent,
        fields: dict,
    ) -> None:
        if event.scheduled_at is None:
            return

        lead_minutes = 15
        raw_lead = fields.get("reminder_lead_minutes")
        if raw_lead is not None:
            lead_minutes = int(raw_lead)
        scheduled_at = event.scheduled_at - timedelta(minutes=lead_minutes)
        content = f"提醒：{event.title}"
        reminders = (
            self._db.query(Reminder)
            .filter(
                Reminder.reminder_type == "life_event_pre_event",
                Reminder.target_type == "life_event",
                Reminder.target_id == event.id,
                Reminder.status.in_(
                    [ReminderStatus.PENDING.value, ReminderStatus.FAILED.value]
                ),
            )
            .all()
        )
        if not reminders:
            crud.create_reminder(
                self._db,
                reminder_type="life_event_pre_event",
                target_type="life_event",
                target_id=event.id,
                scheduled_at=scheduled_at,
                content=content,
            )
            return
        for reminder in reminders:
            reminder.scheduled_at = scheduled_at
            reminder.content = content
            reminder.retry_count = 0
            reminder.status = ReminderStatus.PENDING.value

    def _apply_delete_event(self, pending: PendingOperation) -> PendingOperation:
        payload = pending.operation_payload
        inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        selector = inner.get("selector") or payload.get("selector") or {}
        targets = selector.get("targets")
        if isinstance(targets, list) and targets:
            return self._apply_delete_event_targets(pending, targets)

        event_type = selector.get("event_type")
        resource_id = selector.get("id")

        if resource_id is None:
            pending.status = PendingOperationStatus.FAILED.value
            pending.error_message = "missing event id"
            self._db.commit()
            self._db.refresh(pending)
            return pending

        if event_type == "assignment":
            assignment = self._db.get(Assignment, resource_id)
            if assignment is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"assignment not found: {resource_id}"
                self._db.commit()
                self._db.refresh(pending)
                return pending
            assignment.status = AssignmentStatus.CANCELLED.value
            pending.status = PendingOperationStatus.APPLIED.value
            pending.result_resource_type = "assignment"
            pending.result_resource_id = assignment.id
            pending.error_message = None
            self._db.commit()
            self._db.refresh(pending)
            return pending

        if event_type == "life_event":
            event = self._db.get(LifeEvent, resource_id)
            if event is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"life_event not found: {resource_id}"
                self._db.commit()
                self._db.refresh(pending)
                return pending
            event.status = LifeEventStatus.CANCELLED.value
            pending.status = PendingOperationStatus.APPLIED.value
            pending.result_resource_type = "life_event"
            pending.result_resource_id = event.id
            pending.error_message = None
            self._db.commit()
            self._db.refresh(pending)
            return pending

        if event_type == "course_session":
            session = self._db.get(CourseSession, resource_id)
            if session is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"course_session not found: {resource_id}"
                self._db.commit()
                self._db.refresh(pending)
                return pending

            session_id = session.id
            self._db.delete(session)
            pending.status = PendingOperationStatus.APPLIED.value
            pending.result_resource_type = "course_session"
            pending.result_resource_id = session_id
            pending.error_message = None
            self._db.commit()
            self._db.refresh(pending)
            return pending

        pending.status = PendingOperationStatus.FAILED.value
        pending.error_message = f"unsupported event_type for delete: {event_type}"
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _apply_delete_event_targets(
        self,
        pending: PendingOperation,
        targets: list,
    ) -> PendingOperation:
        normalized_targets: list[tuple[str, int]] = []
        for target in targets:
            if not isinstance(target, dict):
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = "invalid delete target"
                self._db.commit()
                self._db.refresh(pending)
                return pending
            event_type = target.get("event_type")
            resource_id = target.get("id")
            if event_type not in ("assignment", "life_event", "course_session"):
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"unsupported event_type for delete: {event_type!r}"
                self._db.commit()
                self._db.refresh(pending)
                return pending
            if resource_id is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = "missing event id in delete targets"
                self._db.commit()
                self._db.refresh(pending)
                return pending
            if self._get_delete_event(event_type, int(resource_id)) is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"{event_type} not found: {resource_id}"
                pending.result_resource_type = event_type
                pending.result_resource_id = int(resource_id)
                self._db.commit()
                self._db.refresh(pending)
                return pending
            normalized_targets.append((event_type, int(resource_id)))

        last_resource_type: str | None = None
        last_resource_id: int | None = None
        for event_type, resource_id in normalized_targets:
            applied = self._delete_single_event(event_type, resource_id)
            if applied is None:
                pending.status = PendingOperationStatus.FAILED.value
                pending.error_message = f"{event_type} not found: {resource_id}"
                pending.result_resource_type = event_type
                pending.result_resource_id = resource_id
                self._db.commit()
                self._db.refresh(pending)
                return pending
            last_resource_type, last_resource_id = applied

        pending.status = PendingOperationStatus.APPLIED.value
        pending.result_resource_type = last_resource_type
        pending.result_resource_id = last_resource_id
        pending.error_message = None
        self._db.commit()
        self._db.refresh(pending)
        return pending

    def _get_delete_event(self, event_type: str, resource_id: int):
        if event_type == "assignment":
            return self._db.get(Assignment, resource_id)
        if event_type == "life_event":
            return self._db.get(LifeEvent, resource_id)
        if event_type == "course_session":
            return self._db.get(CourseSession, resource_id)
        return None

    def _delete_single_event(
        self,
        event_type: str,
        resource_id: int,
    ) -> tuple[str, int] | None:
        if event_type == "assignment":
            assignment = self._get_delete_event(event_type, resource_id)
            if assignment is None:
                return None
            assignment.status = AssignmentStatus.CANCELLED.value
            return "assignment", assignment.id

        if event_type == "life_event":
            event = self._get_delete_event(event_type, resource_id)
            if event is None:
                return None
            event.status = LifeEventStatus.CANCELLED.value
            return "life_event", event.id

        if event_type == "course_session":
            session = self._get_delete_event(event_type, resource_id)
            if session is None:
                return None
            session_id = session.id
            self._db.delete(session)
            return "course_session", session_id

        return None
