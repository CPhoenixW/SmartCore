from __future__ import annotations

from datetime import datetime
from typing import Any

from app.actions.protocol import map_legacy_event_type, map_status_filter
from app.operations.parser import ParsedOperation

_CREATE_LEGACY_EVENT_TYPE = {
    "assignment": "deadline",
    "life_event": "schedule",
    "course_session": "course",
}


def _map_legacy_create_event_type(event_type: str | None) -> str:
    if event_type in _CREATE_LEGACY_EVENT_TYPE:
        return _CREATE_LEGACY_EVENT_TYPE[event_type]
    if event_type in {"course", "plan", "schedule", "deadline"}:
        return event_type
    return "schedule"


def action_from_parsed(
    parsed: ParsedOperation,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    payload = parsed.payload
    if isinstance(payload.get("action"), str):
        action = dict(payload)
        if now is not None and "request" not in action:
            action["request"] = {
                "timezone": "Asia/Shanghai",
                "now": now.isoformat(),
            }
        return action

    selector = payload.get("selector") or {}
    fields = payload.get("fields") or {}
    action_name = parsed.action_name

    if action_name == "create_event":
        event_type = _map_legacy_create_event_type(fields.get("event_type"))
        event: dict[str, Any] = {
            "event_type": event_type,
            "title": fields.get("title") or fields.get("course_name") or "",
        }
        for key in ("location", "notes"):
            if fields.get(key) is not None:
                event[key] = fields[key]
        if fields.get("start_at"):
            event["start_at"] = fields["start_at"]
        elif fields.get("scheduled_at"):
            event["start_at"] = fields["scheduled_at"]
        elif fields.get("due_at"):
            event["start_at"] = fields["due_at"]
        if fields.get("end_at"):
            event["end_at"] = fields["end_at"]
        elif fields.get("deadline_at") and event_type == "plan":
            event["end_at"] = fields["deadline_at"]
        if (
            fields.get("event_type") == "life_event"
            and not any(fields.get(key) for key in ("start_at", "scheduled_at", "due_at"))
        ):
            event["unscheduled"] = True
        return _base_action(parsed, action_name, {"event": event}, now)

    if action_name == "query_event":
        event_type = map_legacy_event_type(
            selector.get("event_type") or fields.get("event_type")
        )
        status = map_status_filter(selector.get("status") or fields.get("status"))
        filter_payload: dict[str, Any] = {
            "event_type": event_type,
            "status": sorted(status) if status else ["pending", "active"],
            "limit": selector.get("max_candidates")
            or fields.get("max_candidates")
            or 20,
        }
        time_range = selector.get("time_range") or fields.get("time_range")
        if time_range:
            filter_payload["time_range"] = time_range
        semantic: dict[str, Any] = {}
        target_description = selector.get("target_description") or fields.get(
            "target_description"
        )
        if target_description:
            semantic["target_description"] = target_description
        payload_body: dict[str, Any] = {"filter": filter_payload}
        if semantic:
            payload_body["semantic"] = semantic
        return _base_action(parsed, action_name, payload_body, now)

    if action_name in {"update_event", "delete_event"}:
        body: dict[str, Any] = {}
        if selector.get("id") is not None:
            refs = selector.get("refs")
            if not refs:
                legacy_type = selector.get("event_type") or fields.get("event_type")
                body["selector"] = {
                    "mode": "legacy_id",
                    "event_type": legacy_type,
                    "id": selector.get("id"),
                }
            else:
                body["selector"] = selector
        elif selector.get("targets"):
            body["selector"] = {
                "mode": "legacy_targets",
                "targets": selector["targets"],
            }
        else:
            event_type = map_legacy_event_type(selector.get("event_type"))
            selector_body: dict[str, Any] = {
                "mode": "semantic_ref",
                "refs": selector.get("refs") or [],
                "filter": {"event_type": event_type},
            }
            if selector.get("time_range"):
                selector_body["filter"]["time_range"] = selector["time_range"]
            if selector.get("target_description"):
                selector_body["target_description"] = selector["target_description"]
            if action_name == "delete_event":
                selector_body["allow_multiple"] = selector.get("allow_multiple", True)
            body["selector"] = selector_body
        if action_name == "update_event":
            patch = {
                key: value
                for key, value in fields.items()
                if key not in {"event_type"}
            }
            if fields.get("scheduled_at") and "start_at" not in patch:
                patch["start_at"] = fields["scheduled_at"]
            if fields.get("due_at") and "start_at" not in patch:
                patch["start_at"] = fields["due_at"]
            body["patch"] = patch
        return _base_action(parsed, action_name, body, now)

    return _base_action(parsed, action_name, payload, now)


def _base_action(
    parsed: ParsedOperation,
    action_name: str,
    payload_body: dict[str, Any],
    now: datetime | None,
) -> dict[str, Any]:
    action = {
        "action": action_name,
        "source": parsed.source,
        "raw_text": parsed.raw_text,
        "payload": payload_body,
    }
    if now is not None:
        action["request"] = {
            "timezone": "Asia/Shanghai",
            "now": now.isoformat(),
        }
    return action
