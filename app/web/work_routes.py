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
<div class="work-layout">
<aside class="work-sidebar" aria-label="主导航">
  <div class="sidebar-brand">
    <span class="brand-mark">SC</span>
    <span class="brand-text">SmartCore</span>
  </div>
  <nav class="sidebar-nav">
    <button type="button" class="sidebar-link nav-tab" data-view-tab="overview">总览</button>
    <button type="button" class="sidebar-link nav-tab" data-view-tab="evtAdd">添加事件</button>
    <button type="button" class="sidebar-link nav-tab active" data-view-tab="evtBoard">事项看板</button>
    <button type="button" class="sidebar-link nav-tab" data-view-tab="idea">灵感</button>
    <button type="button" class="sidebar-link nav-tab" data-view-tab="course">课程</button>
    <button type="button" class="sidebar-link nav-tab" data-view-tab="dev">设备</button>
    <button type="button" class="sidebar-link nav-tab" data-view-tab="log">日志</button>
    <button type="button" class="sidebar-link nav-tab" data-view-tab="settings">设置</button>
  </nav>
</aside>
<div class="work-content">
  <header class="work-topbar">
    <div class="topbar-search">
      <input class="search-input global-search" id="globalSearch" type="search" placeholder="搜索事项、DDL、灵感、设备日志..." aria-label="全局搜索">
    </div>
    <div class="topbar-meta">
      <div id="topWorkState" class="top-work-state">
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
      <span class="status-pill busy" id="apiStatus">API …</span>
      <span class="live-indicator" id="liveIndicator" aria-live="polite">
        <span class="live-dot" id="liveDot"></span>
        <span id="lastRefresh">—</span>
      </span>
      <button type="button" class="btn btn-sm" data-action="refreshAll">刷新</button>
      <button type="button" class="user-entry" aria-label="用户入口">用户</button>
    </div>
  </header>
  <div class="work-main">
    <main class="view-shell">
      <section class="view" data-view="overview">
        <section class="panel">
          <div class="panel-head"><span>总览</span></div>
          <div class="panel-body">
            <p class="view-desc">SmartCore 个人智能秘书控制台 — 快速掌握今日待办、截止、灵感与设备状态。</p>
            <div class="overview-links">
              <button type="button" class="btn" data-view-tab="evtBoard">进入事项看板</button>
              <button type="button" class="btn" data-view-tab="evtAdd">添加事件</button>
              <button type="button" class="btn" data-view-tab="idea">灵感 Inbox</button>
            </div>
          </div>
        </section>
      </section>
      <section class="view" data-view="evtAdd">
        <section class="panel" id="quickCreatePanel">
          <div class="panel-head"><span>添加事件</span></div>
          <div class="panel-body add-event-layout">
            <section class="natural-input-card">
              <h3>一句话录入</h3>
              <p class="view-desc">输入自然语言描述，解析后预填下方表单，不会直接创建。</p>
              <textarea id="naturalInput" rows="3" placeholder="例如：明天下午3点交作业DDL，高优先级"></textarea>
              <button type="button" class="btn btn-primary" data-action="parseNatural">解析并预填</button>
            </section>
            <section class="form-section">
              <h3>事件表单</h3>
              <div class="form-tabs" role="tablist">
                <button type="button" class="form-tab active" data-create-tab="life">普通事项</button>
                <button type="button" class="form-tab" data-create-tab="ddl">截止事项</button>
                <button type="button" class="form-tab" data-create-tab="course">课程</button>
                <button type="button" class="form-tab" data-create-tab="idea">灵感</button>
              </div>
              <div class="create-tab-pane active" data-create-pane="life">
                <p class="form-pane-label">普通事项</p>
                <form class="quick-form" id="lifeEvtForm" data-endpoint="/api/lifeEvt">
                  <div class="field-group">
                    <label>标题<span class="input-shell"><input name="title" required placeholder="生活事项" autocomplete="off"></span></label>
                    <label>描述<span class="input-shell"><textarea name="desc" placeholder="可选描述"></textarea></span></label>
                    <label>截止时间<span class="input-shell"><input name="dueAt" type="datetime-local"></span></label>
                    <label>优先级<span class="input-shell"><select name="prio"><option value="high">high</option><option value="mid" selected>mid</option><option value="low">low</option></select></span></label>
                  </div>
                  <button type="submit" class="btn btn-primary">创建普通事项</button>
                </form>
              </div>
              <div class="create-tab-pane" data-create-pane="ddl">
                <p class="form-pane-label">截止事项</p>
                <form class="quick-form" id="ddlEvtForm" data-endpoint="/api/ddlEvt">
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
              <div class="create-tab-pane" data-create-pane="course">
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
              <div class="create-tab-pane" data-create-pane="idea">
                <form class="quick-form wide-form" id="ideaForm" data-endpoint="/api/idea">
                  <label>内容<textarea name="content" required placeholder="随手想法、任务雏形、待整理输入"></textarea></label>
                  <button type="submit" class="btn btn-primary">记录 idea</button>
                </form>
              </div>
            </section>
            <section class="create-preview" id="createPreview">
              <h3>创建前预览</h3>
              <div id="createPreviewBody" class="preview-body"><span class="empty">填写表单后将在此显示预览</span></div>
            </section>
            <section class="template-section">
              <h3>常用模板</h3>
              <div class="template-grid">
                <button type="button" class="template-card" data-action="applyTemplate" data-template="homework">作业DDL</button>
                <button type="button" class="template-card" data-action="applyTemplate" data-template="life">生活提醒</button>
                <button type="button" class="template-card" data-action="applyTemplate" data-template="exam">考试复习</button>
                <button type="button" class="template-card" data-action="applyTemplate" data-template="project">项目跟进</button>
              </div>
            </section>
          </div>
        </section>
      </section>
      <section class="view active" data-view="evtBoard">
        <section class="panel" id="evtBoard">
          <div class="panel-head">
            <div>
              <span>事项看板</span>
              <p class="panel-sub">统一查看待办、DDL、灵感和提醒路由</p>
            </div>
            <div class="panel-head-actions">
              <input class="search-input" id="evtSearch" type="search" placeholder="搜索事项…" aria-label="搜索事项">
              <button type="button" class="btn btn-sm" data-action="refreshEvt">刷新</button>
            </div>
          </div>
          <div class="panel-body board-dashboard evt-board-layout">
            <div class="summary-grid">
              <article class="summary-card"><span class="summary-label">今日待办</span><strong id="summaryTodayTodo" class="summary-value">0</strong></article>
              <article class="summary-card"><span class="summary-label">即将截止</span><strong id="summaryDeadline48h" class="summary-value">0</strong></article>
              <article class="summary-card"><span class="summary-label">灵感 Inbox</span><strong id="summaryIdeaInbox" class="summary-value">0</strong></article>
              <article class="summary-card"><span class="summary-label">设备状态</span><strong id="summaryDeviceState" class="summary-value">—</strong></article>
            </div>
            <div class="board-grid">
              <section class="todo-focus board-section">
                <div class="evt-col-head primary" id="todoBoardTitle">todo <span class="count" id="todoCountVisible">0</span></div>
                <h3 class="section-title">今日事项</h3>
                <div id="todayTaskList" class="task-list"></div>
              </section>
              <section class="board-section">
                <h3 class="section-title">未来 48 小时 DDL</h3>
                <div id="deadlineTimeline" class="deadline-timeline"></div>
              </section>
              <section class="board-section">
                <h3 class="section-title">最近灵感</h3>
                <div id="boardIdeaList" class="idea-mini-list"></div>
              </section>
              <section class="board-section">
                <h3 class="section-title">提醒路由</h3>
                <div id="notifyRoutePanel" class="route-panel"></div>
              </section>
            </div>
            <details class="archive-panel" id="evtArchiveDetails">
              <summary>已完成 / 已取消 <span class="count" id="archiveCount">0</span></summary>
              <div class="evt-archive-grid">
                <div class="evt-col"><div class="evt-col-head">done <span class="count" id="doneCount">0</span></div><div id="evtListDone" class="evt-col-list compact-list"></div></div>
                <div class="evt-col"><div class="evt-col-head">cancelled <span class="count" id="cancelledCount">0</span></div><div id="evtListCancelled" class="evt-col-list compact-list"></div></div>
              </div>
            </details>
            <div id="evtListTodo" class="evt-col-list todo-list" hidden aria-hidden="true"></div>
            <span id="todoCount" hidden>0</span>
          </div>
        </section>
      </section>
      <section class="view" data-view="idea">
        <section class="panel">
          <div class="panel-head">
            <div>
              <span>灵感中心</span>
              <p class="panel-sub">沉淀想法、追踪设备状态、保留操作日志</p>
            </div>
          </div>
          <div class="panel-body">
            <form class="quick-form wide-form idea-quick" id="ideaQuickForm" data-endpoint="/api/idea">
              <label>快速记录<textarea name="content" required placeholder="随手想法…"></textarea></label>
              <button type="submit" class="btn btn-primary">保存灵感</button>
            </form>
            <div class="filter-bar">
              <label>筛选
                <select id="ideaStatusFilter">
                  <option value="open">open</option>
                  <option value="handled">handled</option>
                  <option value="archived">archived</option>
                </select>
              </label>
              <button type="button" class="btn btn-sm" data-action="refreshIdea">刷新</button>
            </div>
            <div class="inbox-actions-hint" aria-hidden="true">转事项 · 转 DDL · 归档</div>
            <div id="ideaList" class="inbox-list"></div>
          </div>
        </section>
      </section>
      <section class="view" data-view="course">
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
          <div class="panel-head">
            <span>设备</span>
            <div class="panel-head-actions">
              <label class="inline-filter">筛选
                <select id="devStatusFilter">
                  <option value="">全部状态</option>
                  <option value="working">working</option>
                  <option value="away">away</option>
                  <option value="offline">offline</option>
                </select>
              </label>
              <button type="button" class="btn btn-sm" data-action="refreshDev">刷新</button>
            </div>
          </div>
          <div class="panel-body dev-layout">
            <div id="deviceSummaryCard" class="device-summary-card"></div>
            <section>
              <h3 class="section-title">状态时间线</h3>
              <div id="devStateBody" class="device-timeline"></div>
            </section>
          </div>
        </section>
      </section>
      <section class="view" data-view="log">
        <section class="panel" id="logPanel">
          <div class="panel-head">
            <span>日志</span>
            <div class="panel-head-actions">
              <input class="search-input" id="logKeyword" type="search" placeholder="关键词…" aria-label="日志关键词">
              <select id="logStatusFilter" aria-label="日志状态">
                <option value="">全部状态</option>
                <option value="ok">ok</option>
                <option value="wait">待处理</option>
                <option value="err">err</option>
              </select>
              <button type="button" class="btn btn-sm" data-action="refreshNotify">↻ notify</button>
              <button type="button" class="btn btn-sm" data-action="refreshMsg">↻ msg</button>
              <button type="button" class="btn btn-sm" data-action="refreshAct">↻ act</button>
            </div>
          </div>
          <div class="panel-body">
            <div class="log-tabs" id="logTabs">
              <button type="button" class="log-tab active" data-log-tab="notify" id="notifyLogPanel">notify</button>
              <button type="button" class="log-tab" data-log-tab="msg" id="msgLogPanel">msg</button>
              <button type="button" class="log-tab" data-log-tab="act" id="actLogPanel">act</button>
            </div>
            <div class="log-pane active" data-log-pane="notify"><div id="notifyLogList" class="log-list"></div></div>
            <div class="log-pane" data-log-pane="msg"><div id="msgLogList" class="log-list"></div></div>
            <div class="log-pane" data-log-pane="act"><div id="actLogList" class="log-list"></div></div>
          </div>
        </section>
      </section>
      <section class="view" data-view="settings">
        <section class="panel">
          <div class="panel-head"><span>设置</span></div>
          <div class="panel-body">
            <p class="view-desc">工作台偏好与集成设置（开发中）。</p>
          </div>
        </section>
      </section>
    </main>
    <aside class="context-panel" id="contextPanel">
      <div class="context-head">上下文</div>
      <div class="context-body" id="contextBody">选择视图以查看相关提示与快捷操作。</div>
    </aside>
  </div>
</div>
</div>
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
      <label class="drawer-field" id="evtTimeField">时间<input name="evtTime" type="datetime-local"></label>
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
