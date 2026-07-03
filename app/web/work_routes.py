from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["work"])


@router.get("/work", response_class=HTMLResponse)
def workPage() -> str:
    return """<!doctype html>
<html><head><meta charset="utf-8"><title>SmartCore Work</title></head>
<body>
<h1>SmartCore 工作台</h1>
<ul>
  <li><a href="/api/evt">evt</a></li>
  <li><a href="/api/lifeEvt">lifeEvt</a></li>
  <li><a href="/api/ddlEvt">ddlEvt</a></li>
  <li><a href="/api/courseTpl">courseTpl</a></li>
  <li><a href="/api/courseInst">courseInst</a></li>
  <li><a href="/api/idea">idea</a></li>
  <li><a href="/api/devState">devState</a></li>
  <li><a href="/api/notifyLog">notifyLog</a></li>
  <li><a href="/api/msgLog">msgLog</a></li>
  <li><a href="/api/actLog">actLog</a></li>
</ul>
</body></html>"""
