# ruff: noqa: E501
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["work"])

_WORK_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SmartCore Work</title>
<link rel="stylesheet" href="/static/work/work.css">
</head>
<body data-app="smartcore-work">
<header>
  <h1>SmartCore 工作台</h1>
  <div class="header-meta">
    <span class="status-pill busy" id="apiStatus">API …</span>
    <span id="lastRefresh">—</span>
    <button type="button" class="btn btn-sm" data-action="refreshAll">全部刷新</button>
  </div>
</header>
<div class="layout">
<main>
  <section class="panel" id="quickCreatePanel">
    <div class="panel-head"><span>快速创建</span></div>
    <div class="panel-body">
      <div class="quick-grid">
        <form class="quick-form" id="lifeEvtForm" data-endpoint="/api/lifeEvt">
          <strong>lifeEvt</strong>
          <label for="lifeTitle">标题</label>
          <input id="lifeTitle" name="title" required placeholder="生活事项" autocomplete="off">
          <label for="lifeDueAt">截止时间</label>
          <input id="lifeDueAt" name="dueAt" type="datetime-local">
          <label for="lifePrio">优先级</label>
          <select id="lifePrio" name="prio">
            <option value="high">high</option>
            <option value="mid" selected>mid</option>
            <option value="low">low</option>
          </select>
          <button type="submit" class="btn btn-primary">创建 lifeEvt</button>
        </form>
        <form class="quick-form" id="ddlEvtForm" data-endpoint="/api/ddlEvt">
          <strong>ddlEvt</strong>
          <label for="ddlTitle">标题</label>
          <input id="ddlTitle" name="title" required placeholder="截止日期事项" autocomplete="off">
          <label for="ddlAt">DDL</label>
          <input id="ddlAt" name="ddlAt" type="datetime-local">
          <label for="ddlPrio">优先级</label>
          <select id="ddlPrio" name="prio">
            <option value="high">high</option>
            <option value="mid" selected>mid</option>
            <option value="low">low</option>
          </select>
          <label><input type="checkbox" id="hardDdl" name="hardDdl"> hardDdl</label>
          <button type="submit" class="btn btn-primary">创建 ddlEvt</button>
        </form>
        <form class="quick-form" id="ideaForm" data-endpoint="/api/idea">
          <strong>idea</strong>
          <label for="ideaContent">内容</label>
          <textarea id="ideaContent" name="content" required placeholder="随手想法"></textarea>
          <button type="submit" class="btn btn-primary">创建 idea</button>
        </form>
      </div>
    </div>
  </section>
  <section class="panel" id="evtBoard">
    <div class="panel-head">
      <span>事项看板</span>
      <div class="panel-head-actions">
        <input class="search-input" id="evtSearch" type="search" placeholder="搜索事项…" aria-label="搜索事项">
        <button type="button" class="btn btn-sm" id="refreshEvtBtn" data-action="refreshEvt">刷新</button>
      </div>
    </div>
    <div class="panel-body">
      <div class="evt-columns">
        <div class="evt-col" id="evtColTodo">
          <div class="evt-col-head">todo <span class="count" id="todoCount">0</span></div>
          <div id="evtListTodo"></div>
        </div>
        <div class="evt-col" id="evtColDone">
          <div class="evt-col-head">done <span class="count" id="doneCount">0</span></div>
          <div id="evtListDone"></div>
        </div>
        <div class="evt-col" id="evtColCancelled">
          <div class="evt-col-head">cancelled <span class="count" id="cancelledCount">0</span></div>
          <div id="evtListCancelled"></div>
        </div>
      </div>
    </div>
  </section>
  <section class="panel" id="ideaPanel">
    <div class="panel-head">
      <span>ideas</span>
      <button type="button" class="btn btn-sm" id="refreshIdeaBtn" data-action="refreshIdea">刷新</button>
    </div>
    <div class="panel-body"><div id="ideaList" class="log-list"></div></div>
  </section>
</main>
<aside>
  <section class="panel" id="devStatePanel">
    <div class="panel-head">
      <span>设备状态</span>
      <button type="button" class="btn btn-sm" id="refreshDevBtn" data-action="refreshDev">刷新</button>
    </div>
    <div class="panel-body" id="devStateBody"><span class="empty">暂无设备上报</span></div>
  </section>
  <section class="panel" id="logPanel">
    <div class="panel-head">
      <span>日志</span>
      <div class="panel-head-actions">
        <button type="button" class="btn btn-sm" data-action="refreshNotify">↻ notify</button>
        <button type="button" class="btn btn-sm" data-action="refreshMsg">↻ msg</button>
        <button type="button" class="btn btn-sm" data-action="refreshAct">↻ act</button>
      </div>
    </div>
    <div class="panel-body">
      <div class="log-tabs" id="logTabs">
        <button type="button" class="log-tab active" data-log-tab="notify" id="notifyLogPanel">notifyLog</button>
        <button type="button" class="log-tab" data-log-tab="msg" id="msgLogPanel">msgLog</button>
        <button type="button" class="log-tab" data-log-tab="act" id="actLogPanel">actLog</button>
      </div>
      <div class="log-pane active" data-log-pane="notify"><div id="notifyLogList" class="log-list"></div></div>
      <div class="log-pane" data-log-pane="msg"><div id="msgLogList" class="log-list"></div></div>
      <div class="log-pane" data-log-pane="act"><div id="actLogList" class="log-list"></div></div>
    </div>
  </section>
</aside>
</div>
<div class="flash" id="flash"></div>
<script type="module" src="/static/work/work.js"></script>
</body>
</html>"""


@router.get("/work", response_class=HTMLResponse)
def workPage() -> str:
    return _WORK_HTML
