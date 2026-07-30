from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import PurePath
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.server.new_core.models import (
    CodexWorkReport,
    ComputerActivityContext,
    ComputerWorkBlock,
    EvtBase,
    PlanEvt,
)

OTHER_PROJECT_KEY = "__other_work__"
OTHER_PROJECT_NAME = "其他工作"
_STATUS_ORDER = {"completed": 0, "partial": 1, "in_progress": 2}
_MAX_CONTEXT_EVIDENCE_ITEMS = 5
_MAX_DAILY_REPORTS = 100
_MAX_DAILY_WORK_BLOCKS = 300
_MAX_DAILY_PLANS = 500


def _aware(value: str | None, timezone: ZoneInfo) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone) if parsed.tzinfo is None else parsed


def _normalize(value: object) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").casefold())


def _project_aliases(project_key: str, project_name: str) -> set[str]:
    values = {project_name}
    try:
        values.add(PurePath(project_key).name)
    except ValueError:
        pass
    if "/" not in project_key and "\\" not in project_key:
        values.add(project_key)
    aliases = {_normalize(value) for value in values}
    for value in values:
        aliases.update(
            _normalize(token)
            for token in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", str(value))
            if len(_normalize(token)) >= 3
        )
    return {value for value in aliases if len(value) >= 3}


def _match_score(aliases: set[str], evidence: list[str]) -> int:
    score = 0
    for raw in evidence:
        value = _normalize(raw)
        if not value:
            continue
        for alias in aliases:
            if value == alias:
                score = max(score, 4)
            elif len(alias) >= 4 and (alias in value or value in alias):
                score = max(score, 2)
    return score


def _project_for_evidence(
    projects: dict[str, dict[str, Any]], evidence: list[str]
) -> str | None:
    scored = sorted(
        (
            (_match_score(set(project["aliases"]), evidence), project_key)
            for project_key, project in projects.items()
            if project_key != OTHER_PROJECT_KEY
        ),
        reverse=True,
    )
    if not scored or scored[0][0] < 2:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][1]


def _report_dict(row: CodexWorkReport) -> dict[str, Any]:
    evidence = row.evidence if isinstance(row.evidence, dict) else {}
    compact_evidence = {
        key: [str(item) for item in value[:_MAX_CONTEXT_EVIDENCE_ITEMS]]
        for key in ("commits", "pullRequests", "tests")
        if isinstance((value := evidence.get(key)), list)
    }
    return {
        "reportId": row.reportId,
        "sourceTaskId": row.sourceTaskId,
        "projectKey": row.projectKey,
        "projectName": row.projectName,
        "title": row.title,
        "summary": row.summary,
        "status": row.status,
        "startedAt": row.startedAt,
        "endedAt": row.endedAt,
        "evidence": compact_evidence,
    }


def _block_dict(row: ComputerWorkBlock) -> dict[str, Any]:
    return {
        "blockId": row.blockId,
        "deviceId": row.deviceId,
        "startAt": row.startAt,
        "endAt": row.endAt,
        "title": row.title,
        "summary": row.summary,
        "progress": row.progress,
        "outcome": row.outcome,
        "blocker": row.blocker,
        "nextStep": row.nextStep,
        "activeSeconds": row.activeSeconds,
        "plannedActiveSeconds": row.plannedActiveSeconds,
        "primaryApps": row.primaryApps or [],
        "planAssessments": row.planAssessments or [],
    }


def _plan_dict(base: EvtBase, plan: PlanEvt, timezone: ZoneInfo) -> dict[str, Any]:
    start = _aware(plan.stTime, timezone)
    end = start + timedelta(minutes=max(1, plan.durationMin)) if start else None
    return {
        "evtId": base.evtId,
        "title": base.title,
        "description": base.desc,
        "status": base.stat,
        "startAt": start.isoformat() if start else plan.stTime,
        "endAt": end.isoformat() if end else None,
    }


def _project_state(project: dict[str, Any]) -> str | None:
    statuses = [str(item.get("status")) for item in project["codexReports"]]
    return max(statuses, key=lambda item: _STATUS_ORDER.get(item, -1)) if statuses else None


def build_daily_work_context(
    db: Session,
    *,
    user_id: str,
    report_date: str,
    timezone_name: str = "Asia/Shanghai",
    device_id: str | None = None,
) -> dict[str, Any]:
    try:
        timezone = ZoneInfo(timezone_name)
        local_start = datetime.fromisoformat(report_date).replace(tzinfo=timezone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError("date and timezone must identify a valid local day") from exc
    local_end = local_start + timedelta(days=1)

    report_filters = [
        CodexWorkReport.userId == user_id,
        CodexWorkReport.reportDate == report_date,
    ]
    block_filters = [
        ComputerWorkBlock.userId == user_id,
        ComputerWorkBlock.localDate == report_date,
    ]
    if device_id is not None:
        report_filters.append(CodexWorkReport.deviceId == device_id)
        block_filters.append(ComputerWorkBlock.deviceId == device_id)
    reports = list(
        db.scalars(
            select(CodexWorkReport)
            .where(*report_filters)
            .order_by(CodexWorkReport.projectName, CodexWorkReport.createdAt)
            .limit(_MAX_DAILY_REPORTS)
        )
    )
    blocks = list(
        db.scalars(
            select(ComputerWorkBlock)
            .where(*block_filters)
            .order_by(ComputerWorkBlock.startAt)
            .limit(_MAX_DAILY_WORK_BLOCKS)
        )
    )
    plans = [
        (base, plan)
        for base, plan in db.execute(
            select(EvtBase, PlanEvt)
            .join(PlanEvt, PlanEvt.evtId == EvtBase.evtId)
            .where(EvtBase.userId == user_id, EvtBase.evtType == "plan")
            .order_by(PlanEvt.stTime)
        ).all()
        if (
            (start := _aware(plan.stTime, timezone)) is not None
            and start < local_end
            and start + timedelta(minutes=max(1, plan.durationMin)) > local_start
        )
    ][:_MAX_DAILY_PLANS]

    projects: dict[str, dict[str, Any]] = {}
    for report in reports:
        project = projects.setdefault(
            report.projectKey,
            {
                "projectKey": report.projectKey,
                "projectName": report.projectName,
                "aliases": _project_aliases(report.projectKey, report.projectName),
                "activeSeconds": 0,
                "plannedActiveSeconds": 0,
                "codexReports": [],
                "workBlocks": [],
                "plans": [],
            },
        )
        project["codexReports"].append(_report_dict(report))

    context_ids = {
        str(context_id)
        for block in blocks
        for context_id in (block.contextIds or [])
        if context_id
    }
    contexts_by_id: dict[str, ComputerActivityContext] = {}
    if context_ids:
        contexts_by_id = {
            row.contextId: row
            for row in db.scalars(
                select(ComputerActivityContext).where(
                    ComputerActivityContext.userId == user_id,
                    ComputerActivityContext.contextId.in_(context_ids),
                )
            )
        }

    unmatched_blocks: list[ComputerWorkBlock] = []
    for block in blocks:
        evidence = [
            value
            for value in (block.topicKey, block.title, block.summary)
            if isinstance(value, str) and value
        ]
        for context_id in block.contextIds or []:
            context = contexts_by_id.get(str(context_id))
            if context is None or context.titleRedacted:
                continue
            evidence.extend(
                value
                for value in (
                    context.workspace,
                    context.documentName,
                    context.windowTitle,
                )
                if isinstance(value, str) and value
            )
        project_key = _project_for_evidence(projects, evidence)
        if project_key is None:
            unmatched_blocks.append(block)
            continue
        project = projects[project_key]
        project["activeSeconds"] += max(0, int(block.activeSeconds or 0))
        project["plannedActiveSeconds"] += max(0, int(block.plannedActiveSeconds or 0))
        project["workBlocks"].append(_block_dict(block))

    unmatched_plans: list[tuple[EvtBase, PlanEvt]] = []
    for base, plan in plans:
        project_key = _project_for_evidence(
            projects,
            [value for value in (base.title, base.desc) if value],
        )
        if project_key is None:
            unmatched_plans.append((base, plan))
        else:
            projects[project_key]["plans"].append(_plan_dict(base, plan, timezone))

    if unmatched_blocks or unmatched_plans:
        other = {
            "projectKey": OTHER_PROJECT_KEY,
            "projectName": OTHER_PROJECT_NAME,
            "aliases": set(),
            "activeSeconds": sum(max(0, int(row.activeSeconds or 0)) for row in unmatched_blocks),
            "plannedActiveSeconds": sum(
                max(0, int(row.plannedActiveSeconds or 0)) for row in unmatched_blocks
            ),
            "codexReports": [],
            "workBlocks": [_block_dict(row) for row in unmatched_blocks],
            "plans": [_plan_dict(base, plan, timezone) for base, plan in unmatched_plans],
        }
        projects[OTHER_PROJECT_KEY] = other

    output_projects: list[dict[str, Any]] = []
    for project in projects.values():
        statuses: dict[str, int] = defaultdict(int)
        for report in project["codexReports"]:
            statuses[str(report["status"])] += 1
        output_projects.append(
            {
                key: value
                for key, value in {
                    **project,
                    "status": _project_state(project),
                    "statusCounts": {
                        "completed": statuses["completed"],
                        "partial": statuses["partial"],
                        "inProgress": statuses["in_progress"],
                    },
                }.items()
                if key != "aliases"
            }
        )
    output_projects.sort(
        key=lambda item: (
            item["projectKey"] == OTHER_PROJECT_KEY,
            -int(item["activeSeconds"]),
            str(item["projectName"]).casefold(),
        )
    )
    return {
        "date": report_date,
        "timezone": timezone_name,
        "projects": output_projects,
        "codexReports": [_report_dict(row) for row in reports],
        "computerWorkBlocks": [_block_dict(row) for row in blocks],
        "plans": [_plan_dict(base, plan, timezone) for base, plan in plans],
        "totals": {
            "activeSeconds": sum(int(row.activeSeconds or 0) for row in blocks),
            "plannedActiveSeconds": sum(int(row.plannedActiveSeconds or 0) for row in blocks),
            "codexReportCount": len(reports),
            "projectCount": len([item for item in output_projects if item["codexReports"]]),
        },
        "evidencePriority": ["human_completion", "codex_report", "work_block"],
        "associationPolicy": "conservative_unique_match",
    }
