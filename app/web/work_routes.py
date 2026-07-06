from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["work"])

_PAGE_META = {
    "overview": ("总览", "快速查看待办、截止事项、灵感与快捷入口"),
    "add": ("添加事件", "创建普通事项、截止事项，并支持自然语言预填"),
    "update": ("更新事件", "查看、修改、完成、取消已有事件"),
    "inspire": ("灵感", "添加、查看、整理灵感，并转换为事项"),
    "course": ("课表", "查看和修改课程模板、课程实例"),
    "log": ("日志", "查看事件增删改查和系统操作记录"),
}

_NAV = [
    ("overview", "/work", "总览", "⌂"),
    ("add", "/work/add", "添加事件", "+"),
    ("update", "/work/update", "更新事件", "✎"),
    ("inspire", "/work/inspire", "灵感", "◇"),
    ("course", "/work/course", "课表", "□"),
    ("log", "/work/log", "日志", "≡"),
]


def _nav_html(active: str) -> str:
    return "\n".join(
        f'<a class="nav-link {"active" if key == active else ""}" href="{href}"><span class="nav-ico">{icon}</span>{label}</a>'
        for key, href, label, icon in _NAV
    )


def _shell(active: str, body_html: str) -> str:
    title, subtitle = _PAGE_META[active]
    script_src = "/static/work/work_events.js" if active in {"overview", "update"} else "/static/work/work_v2.js"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SmartCore Work - {title}</title>
<link rel="stylesheet" href="/static/work/work_v2.css">
</head>
<body data-page="{active}">
<div class="work-layout">
  <aside class="work-sidebar">
    <a class="brand" href="/work" aria-label="SmartCore Work">
      <span class="brand-mark">SC</span>
      <span><strong>SmartCore</strong><small>学生智能助手</small></span>
    </a>
    <nav class="work-nav" aria-label="工作台导航">
      {_nav_html(active)}
    </nav>
  </aside>
  <section class="work-content">
    <header class="topbar">
      <label class="top-search"><span>⌕</span><input id="globalSearch" placeholder="搜索事项、DDL、灵感、日志..." autocomplete="off"></label>
      <div class="topbar-actions">
        <span class="status-pill" id="apiStatus">API 待命</span>
        <span class="top-muted" id="lastRefresh">未刷新</span>
        <button type="button" class="btn" id="refreshPageBtn">刷新</button>
      </div>
    </header>
    <main class="page-main">
      <section class="page-head">
        <div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
      </section>
      {body_html}
    </main>
  </section>
</div>
<div class="toast" id="toast"></div>
<script type="module" src="{script_src}"></script>
</body>
</html>"""

_EVT_EDIT_FORM = """
<form id="evtEditForm" class="edit-form">
  <input name="evtId" type="hidden">
  <label class="field required"><span>标题</span><input name="title" required></label>
  <label class="field"><span>描述</span><textarea name="desc" rows="4"></textarea></label>
  <div class="form-row"><label class="field"><span>状态</span><select name="stat"><option value="todo">待办</option><option value="done">完成</option><option value="cancelled">已取消</option></select></label><label class="field"><span>优先级</span><select name="prio"><option value="mid">中</option><option value="high">高</option><option value="low">低</option></select></label></div>
  <label class="field" id="evtTimeField"><span>时间</span><input name="evtTime" type="datetime-local"></label>
  <label class="check-line" id="hardDdlField"><input name="hardDdl" type="checkbox"><span>硬性截止</span></label>
  <div class="button-row"><button type="submit" class="btn btn-primary">保存</button><button type="button" class="btn" id="markDoneBtn">完成</button><button type="button" class="btn btn-danger" id="cancelEvtBtn">取消</button></div>
</form>
"""

_OVERVIEW_BODY = f"""
<section class="summary-grid">
  <article class="summary-card"><span>待办事项</span><strong id="ovTodo">0</strong></article>
  <article class="summary-card"><span>今日事项</span><strong id="ovToday">0</strong></article>
  <article class="summary-card"><span>未来 48 小时</span><strong id="ovDeadline">0</strong></article>
  <article class="summary-card"><span>灵感 Inbox</span><strong id="ovIdeas">0</strong></article>
</section>
<section class="content-grid two-one overview-grid">
  <article class="card"><header><h2>今日事项</h2><a class="link" href="/work/update">全部事件</a></header><div class="card-body list" id="overviewTasks"></div></article>
  <aside class="card sticky-card"><header><h2>编辑事件</h2></header><div class="card-body">{_EVT_EDIT_FORM}</div></aside>
</section>
<section class="content-grid two">
  <article class="card"><header><h2>即将截止</h2></header><div class="card-body list" id="overviewTimeline"></div></article>
  <article class="card"><header><h2>最近灵感</h2><a class="link" href="/work/inspire">整理</a></header><div class="card-body list" id="overviewIdeas"></div></article>
</section>
<section class="content-grid two">
  <a class="card quick-card" href="/work/add"><div class="card-body"><strong>添加事件</strong><p class="row-meta">创建事项或 DDL</p></div></a>
  <a class="card quick-card" href="/work/inspire"><div class="card-body"><strong>记录灵感</strong><p class="row-meta">保存想法并转事项</p></div></a>
</section>
"""

_ADD_BODY = """
<section class="content-grid two-one">
  <div class="stack">
    <article class="card">
      <header><h2>自然语言录入</h2><button type="button" class="btn btn-primary" id="parseNaturalBtn">解析并预填</button></header>
      <div class="card-body"><textarea id="naturalText" class="nl-input" rows="3" placeholder="例如：明天晚上八点提醒我复习热流体，优先级高"></textarea></div>
    </article>
    <article class="card">
      <header><h2>事件表单</h2><div class="tabs"><button class="tab active" data-create-tab="life">普通事项</button><button class="tab" data-create-tab="ddl">截止事项</button></div></header>
      <div class="card-body">
        <form id="lifeForm" class="form-pane active" data-endpoint="/api/lifeEvt">
          <label class="field required"><span>标题</span><input name="title" required placeholder="例如：洗衣服"></label>
          <label class="field"><span>描述</span><textarea name="desc" rows="3"></textarea></label>
          <div class="form-row"><label class="field"><span>提醒时间</span><input name="dueAt" type="datetime-local"></label><label class="field"><span>优先级</span><select name="prio"><option value="mid">中</option><option value="high">高</option><option value="low">低</option></select></label></div>
          <button class="btn btn-primary btn-block" type="submit">创建普通事项</button>
        </form>
        <form id="ddlForm" class="form-pane" data-endpoint="/api/ddlEvt">
          <label class="field required"><span>标题</span><input name="title" required placeholder="例如：复习热流体"></label>
          <label class="field"><span>描述</span><textarea name="desc" rows="3"></textarea></label>
          <div class="form-row"><label class="field required"><span>截止时间</span><input name="ddlAt" type="datetime-local" required></label><label class="field"><span>优先级</span><select name="prio"><option value="mid">中</option><option value="high">高</option><option value="low">低</option></select></label></div>
          <label class="check-line"><input name="hardDdl" type="checkbox"><span>硬性截止</span></label>
          <button class="btn btn-primary btn-block" type="submit">创建截止事项</button>
        </form>
      </div>
    </article>
  </div>
  <aside class="stack">
    <article class="card"><header><h2>创建前预览</h2></header><div class="card-body" id="createPreview"></div></article>
    <article class="card"><header><h2>常用模板</h2></header><div class="card-body template-grid"><button class="template" data-template="homework">作业 DDL</button><button class="template" data-template="life">生活提醒</button><button class="template" data-template="exam">考试复习</button><button class="template" data-template="project">项目跟进</button></div></article>
  </aside>
</section>
"""

_UPDATE_BODY = f"""
<section class="content-grid two-one">
  <article class="card"><header><h2>事件列表</h2><select id="evtStatusFilter"><option value="todo">待办</option><option value="done">完成</option><option value="cancelled">已取消</option><option value="all">全部</option></select></header><div class="card-body list" id="evtList"></div></article>
  <aside class="card sticky-card"><header><h2>编辑事件</h2></header><div class="card-body">{_EVT_EDIT_FORM}</div></aside>
</section>
"""

_INSPIRE_BODY = """
<section class="content-grid two-one">
  <article class="card"><header><h2>记录灵感</h2><button type="button" class="btn btn-primary" id="saveIdeaBtn">保存</button></header><div class="card-body"><textarea id="ideaContent" class="nl-input" rows="5" placeholder="记录想法、任务雏形、临时计划..."></textarea></div></article>
  <aside class="card"><header><h2>转事项</h2></header><div class="card-body"><form id="ideaToEvtForm"><input name="ideaId" type="hidden"><label class="field"><span>来源灵感</span><input name="ideaTitle" disabled></label><label class="field required"><span>事项标题</span><input name="title" required></label><label class="field"><span>提醒时间</span><input name="dueAt" type="datetime-local"></label><button type="submit" class="btn btn-primary btn-block">转为普通事项</button></form></div></aside>
</section>
<section class="card"><header><h2>灵感列表</h2><select id="ideaFilter"><option value="open">open</option><option value="handled">handled</option><option value="all">全部</option></select></header><div class="card-body list" id="ideaList"></div></section>
"""

_COURSE_BODY = """
<section class="content-grid two-one">
  <article class="card"><header><h2>课程模板</h2><button class="btn btn-primary" id="newCourseBtn">新建模板</button></header><div class="card-body list" id="courseTplList"></div></article>
  <aside class="card"><header><h2>编辑课程模板</h2></header><div class="card-body"><form id="courseTplForm" class="edit-form"><input name="tplId" type="hidden"><label class="field required"><span>课程名称</span><input name="courseName" required></label><div class="form-row"><label class="field"><span>教师</span><input name="teacher"></label><label class="field"><span>教室</span><input name="room"></label></div><div class="form-row"><label class="field required"><span>星期</span><input name="weekday" type="number" min="1" max="7" required></label><label class="field"><span>周属性</span><select name="weekMode"><option value="all">全部</option><option value="odd">单周</option><option value="even">双周</option></select></label></div><div class="form-row"><label class="field"><span>开始</span><input name="startTime" type="time"></label><label class="field"><span>结束</span><input name="endTime" type="time"></label></div><div class="form-row"><label class="field"><span>起始周</span><input name="startWeek" type="number" min="1"></label><label class="field"><span>结束周</span><input name="endWeek" type="number" min="1"></label></div><label class="field"><span>学期</span><input name="semester" placeholder="2026-fall"></label><div class="button-row"><button type="submit" class="btn btn-primary">保存模板</button><button type="button" class="btn btn-danger" id="deleteCourseTplBtn">删除模板</button></div></form></div></aside>
</section>
<section class="card"><header><h2>课程实例</h2></header><div class="card-body list" id="courseInstList"></div></section>
"""

_LOG_BODY = """
<section class="card"><header><h2>操作日志</h2><div class="tabs"><button class="tab active" data-log-tab="act">事件操作</button><button class="tab" data-log-tab="notify">提醒</button><button class="tab" data-log-tab="msg">消息</button></div></header><div class="card-body"><div class="filter-row"><input id="logKeyword" placeholder="搜索日志..." autocomplete="off"><select id="logStatusFilter"><option value="">全部状态</option><option value="ok">ok</option><option value="err">err</option><option value="pending">pending</option></select></div><div id="logList" class="list"></div></div></section>
"""


@router.get("/work", response_class=HTMLResponse)
def workOverview() -> str:
    return _shell("overview", _OVERVIEW_BODY)


@router.get("/work/add", response_class=HTMLResponse)
def workAdd() -> str:
    return _shell("add", _ADD_BODY)


@router.get("/work/update", response_class=HTMLResponse)
def workUpdate() -> str:
    return _shell("update", _UPDATE_BODY)


@router.get("/work/inspire", response_class=HTMLResponse)
def workInspire() -> str:
    return _shell("inspire", _INSPIRE_BODY)


@router.get("/work/course", response_class=HTMLResponse)
def workCourse() -> str:
    return _shell("course", _COURSE_BODY)


@router.get("/work/log", response_class=HTMLResponse)
def workLog() -> str:
    return _shell("log", _LOG_BODY)
