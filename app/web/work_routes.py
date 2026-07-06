from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["work"])


@router.get("/work")
def workPage() -> RedirectResponse:
    return RedirectResponse(url="/work/board", status_code=307)
