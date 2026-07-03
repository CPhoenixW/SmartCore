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
<body data-app="smartcore-work" data-theme="light">
<header class="app-header">
  <div class="header-brand">
    <h1>SmartCore 工作台</h1>
    <div class="work-state" id="currentWorkState" data-state="unknown">
      <div class="presence-card" id="piStateCard">
        <span class="work-state-label" id="workStateLabel">未知</span>
        <span class="work-state-meta">
          <span id="workStateSource">暂无设备</span>
          <span id="workStateAge">—</span>
        </span>
      </div>
    </div>
  </div>
  <div class="header-meta">
    <span class="status-pill busy" id="apiStatus">API …</span>
    <span class="live-indicator" id="liveIndicator" aria-live="polite">
      <span class="live-dot" id="liveDot"></span>
      <span id="lastRefresh">—</span>
    </span>
    <button type="button" class="btn btn-sm" data-action="refreshAll">全部刷新</button>
  </div>
</header>
<nav class="work-nav" aria-label="工作台视图">
  <button type="button" class="nav-tab active" data-view-tab="evtAdd">添加事件</button>
  <button type="button" class="nav-tab" data-view-tab="evtBoard">事项看板</button>
  <button type="button" class="nav-tab" data-view-tab="idea">灵感</button>
  <button type="button" class="nav-tab" data-view-tab="course">课程</button>
  <button type="button" class="nav-tab" data-view-tab="dev">设备</button>
  <button type="button" class="nav-tab" data-view-tab="log">日志</button>
</nav>
<main class="view-shell">
  <section class="view active" data-view="evtAdd">
    <section class="panel" id="quickCreatePanel">
      <div class="panel-head"><span>添加事件</span></div>
      <div class="panel-body quick-grid">
        <form class="quick-form" id="lifeEvtForm" data-endpoint="/api/lifeEvt">
          <strong>普通事项</strong>
          <div class="field-group">
            <label>标题<span class="input-shell"><input name="title" required placeholder="生活事项" autocomplete="off"></span></label>
            <label>描述<span class="input-shell"><textarea name="desc" placeholder="可选描述"></textarea></span></label>
            <label>截止时间<span class="input-shell"><input name="dueAt" type="datetime-local"></span></label>
            <label>优先级<span class="input-shell"><select name="prio"><option value="high">high</option><option value="mid" selected>mid</option><option value="low">low</option></select></span></label>
          </div>
          <button type="submit" class="btn btn-primary">创建普通事项</button>
        </form>
        <form class="quick-form" id="ddlEvtForm" data-endpoint="/api/ddlEvt">
          <strong>截止事项</strong>
          <div class="field-group">
            <label>标题<span class="input-shell"><input name="title" required placeholder="截止日期事项" autocomplete="off"></span></label>
            <label>描述<span class="input-shell"><textarea name="desc" placeholder="可选描述"></textarea></span></label>
            <label>截止时间<span class="input-shell"><input name="ddlAt" type="datetime-local"></span></label>
            <label>优先级<span class="input-shell"><select name="prio"><option value="high">high</option><option value="mid" selected>mid</option><option value="low">low</option></select></span></label>
            <label class="check-line"><input type="checkbox" name="hardDdl"> 硬性截止</label>
          </div>
          <button type="submit" class="btn btn-primary">创建截止事项</button>
        </form>
      </div>
    </section>
  </section>
  <section class="view" data-view="evtBoard">
    <section class="panel" id="evtBoard">
      <div class="panel-head">
        <span>事项看板</span>
        <div class="panel-head-actions">
          <input class="search-input" id="evtSearch" type="search" placeholder="搜索事项…" aria-label="搜索事项">
          <button type="button" class="btn btn-sm" data-action="refreshEvt">刷新</button>
        </div>
      </div>
      <div class="panel-body evt-columns">
        <div class="evt-col"><div class="evt-col-head">todo <span class="count" id="todoCount">0</span></div><div id="evtListTodo" class="evt-col-list"></div></div>
        <div class="evt-col"><div class="evt-col-head">done <span class="count" id="doneCount">0</span></div><div id="evtListDone" class="evt-col-list"></div></div>
        <div class="evt-col"><div class="evt-col-head">cancelled <span class="count" id="cancelledCount">0</span></div><div id="evtListCancelled" class="evt-col-list"></div></div>
      </div>
    </section>
  </section>
  <section class="view" data-view="idea">
    <section class="panel">
      <div class="panel-head"><span>灵感</span></div>
      <div class="panel-body">
        <form class="quick-form wide-form" id="ideaForm" data-endpoint="/api/idea">
          <label>内容<textarea name="content" required placeholder="随手想法、任务雏形、待整理输入"></textarea></label>
          <button type="submit" class="btn btn-primary">记录 idea</button>
        </form>
      </div>
    </section>
    <section class="panel" id="ideaPanel">
      <div class="panel-head"><span>ideas</span><button type="button" class="btn btn-sm" data-action="refreshIdea">刷新</button></div>
      <div class="panel-body"><div id="ideaList" class="list-stack"></div></div>
    </section>
  </section>
  <section class="view" data-view="course">
    <section class="panel">
      <div class="panel-head"><span>课表模板</span></div>
      <div class="panel-body">
        <form class="quick-form form-grid" id="courseTplForm" data-endpoint="/api/courseTpl">
          <label>课程名称<input name="courseName" required></label>
          <label>教师<input name="teacher"></label>
          <label>教室<input name="room"></label>
          <label>星期<input name="weekday" type="number" min="1" max="7" required></label>
          <label>开始<input name="startTime" type="time"></label>
          <label>结束<input name="endTime" type="time"></label>
          <label>起始周<input name="startWeek" type="number" min="1"></label>
          <label>结束周<input name="endWeek" type="number" min="1"></label>
          <label>周属性<select name="weekMode"><option value="all">all</option><option value="odd">odd</option><option value="even">even</option></select></label>
          <label>学期<input name="semester" placeholder="2026-fall"></label>
          <button type="submit" class="btn btn-primary">创建 courseTpl</button>
        </form>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head"><span>课程实例</span></div>
      <div class="panel-body">
        <form class="quick-form form-grid" id="courseInstForm" data-endpoint="/api/courseInst">
          <label>标题<input name="title" required></label>
          <label>模板ID<input name="tplId" required></label>
          <label>上课日期<input name="classDate" type="date"></label>
          <label>出勤<select name="attendStat"><option value="unknown">unknown</option><option value="present">present</option><option value="absent">absent</option><option value="late">late</option></select></label>
          <button type="submit" class="btn btn-primary">创建 courseInst</button>
        </form>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head"><span>课程列表</span><button type="button" class="btn btn-sm" data-action="refreshCourse">刷新</button></div>
      <div class="panel-body split-lists"><div><h3>courseTpl</h3><div id="courseTplList" class="list-stack"></div></div><div><h3>courseInst</h3><div id="courseInstList" class="list-stack"></div></div></div>
    </section>
  </section>
  <section class="view" data-view="dev">
    <section class="panel" id="devStatePanel">
      <div class="panel-head"><span>设备状态</span><button type="button" class="btn btn-sm" data-action="refreshDev">刷新</button></div>
      <div class="panel-body" id="devStateBody"><span class="empty">暂无设备上报</span></div>
    </section>
  </section>
  <section class="view" data-view="log">
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
        <div class="log-pane active" data-log-pane="notify"><div id="notifyLogList" class="list-stack"></div></div>
        <div class="log-pane" data-log-pane="msg"><div id="msgLogList" class="list-stack"></div></div>
        <div class="log-pane" data-log-pane="act"><div id="actLogList" class="list-stack"></div></div>
      </div>
    </section>
  </section>
</main>
<div id="evtDetailDrawer" class="evt-detail-drawer" aria-hidden="true">
  <div class="evt-detail-backdrop" data-action="closeEvtDetail"></div>
  <aside class="evt-detail-panel" role="dialog" aria-labelledby="evtDetailTitle">
    <div class="evt-detail-head">
      <h2 id="evtDetailTitle">事项详情</h2>
      <button type="button" class="btn btn-sm evt-detail-close" data-action="closeEvtDetail" aria-label="关闭">×</button>
    </div>
    <form id="evtDetailForm" class="drawer-form">
      <label class="drawer-field">标题<input name="title" required autocomplete="off"></label>
      <label class="drawer-field">描述<textarea name="desc" rows="4" placeholder="可选描述"></textarea></label>
      <label class="drawer-field">状态<select name="stat"><option value="todo">待办</option><option value="done">完成</option><option value="cancelled">已取消</option></select></label>
      <label class="drawer-field">优先级<select name="prio"><option value="high">高</option><option value="mid">中</option><option value="low">低</option></select></label>
      <div class="drawer-form-actions">
        <button type="button" class="btn btn-primary" data-action="saveEvtDetail">保存</button>
        <button type="button" class="btn btn-success" id="completeEvtDetailBtn" data-action="completeEvtDetail">完成</button>
        <button type="button" class="btn btn-danger" id="cancelEvtDetailBtn" data-action="cancelEvtDetail">取消事项</button>
        <button type="button" class="btn" id="reopenEvtDetailBtn" data-action="reopenEvtDetail" hidden>恢复为待办</button>
      </div>
    </form>
  </aside>
</div>
<div class="flash" id="flash"></div>
<script type="module" src="/static/work/work.js"></script>
</body>
</html>"""


@router.get("/work", response_class=HTMLResponse)
def workPage() -> str:
    return _WORK_HTML
