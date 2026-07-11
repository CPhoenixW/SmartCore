from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.web.device_routes import work_device
from app.web.work_routes import (
    workAdd,
    workCourse,
    workInspire,
    workLog,
    workOverview,
    workSettings,
    workUpdate,
)

router = APIRouter(tags=["work-legacy"])


def _legacy_html(factory: Callable[[], str]) -> str:
    return factory().replace('href="/work', 'href="/work-legacy')


@router.get("/work-legacy", response_class=HTMLResponse, include_in_schema=False)
def legacy_overview() -> str:
    return _legacy_html(workOverview)


@router.get("/work-legacy/add", response_class=HTMLResponse, include_in_schema=False)
def legacy_add() -> str:
    return _legacy_html(workAdd)


@router.get("/work-legacy/update", response_class=HTMLResponse, include_in_schema=False)
def legacy_update() -> str:
    return _legacy_html(workUpdate)


@router.get("/work-legacy/inspire", response_class=HTMLResponse, include_in_schema=False)
def legacy_inspire() -> str:
    return _legacy_html(workInspire)


@router.get("/work-legacy/course", response_class=HTMLResponse, include_in_schema=False)
def legacy_course() -> str:
    return _legacy_html(workCourse)


@router.get("/work-legacy/log", response_class=HTMLResponse, include_in_schema=False)
def legacy_log() -> str:
    return _legacy_html(workLog)


@router.get("/work-legacy/settings", response_class=HTMLResponse, include_in_schema=False)
def legacy_settings() -> str:
    return _legacy_html(workSettings)


@router.get("/work-legacy/device", response_class=HTMLResponse, include_in_schema=False)
def legacy_device() -> str:
    return _legacy_html(work_device)
