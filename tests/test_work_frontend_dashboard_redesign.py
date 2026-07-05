from fastapi.testclient import TestClient

from app.main import create_app


def _work_assets(app_env) -> tuple[str, str, str]:
    client = TestClient(create_app())
    return (
        client.get("/work").text,
        client.get("/static/work/work.css").text,
        client.get("/static/work/work.js").text,
    )


def test_work_uses_sidebar_topbar_and_context_panel_layout(app_env) -> None:
    html, css, js = _work_assets(app_env)

    assert 'class="work-layout"' in html
    assert 'class="work-sidebar"' in html
    assert 'class="work-content"' in html
    assert 'class="work-topbar"' in html
    assert 'class="context-panel"' in html
    assert 'id="globalSearch"' in html
    assert 'placeholder="搜索事项、DDL、灵感、设备日志..."' in html
    assert 'id="topWorkState"' in html
    assert 'id="apiStatus"' in html
    assert 'id="lastRefresh"' in html
    assert 'class="user-entry"' in html

    for label in ("总览", "添加事件", "事项看板", "灵感", "课程", "设备", "日志", "设置"):
        assert label in html

    assert ".work-layout" in css
    assert ".work-sidebar" in css
    assert "width: 240px" in css
    assert ".work-topbar" in css
    assert ".context-panel" in css
    assert "background: #f5f7fb" in css.lower()
    assert "#2563eb" in css.lower()
    assert "linear-gradient(135deg" not in css
    assert "letter-spacing: -" not in css

    assert "evtBoard" in js
    assert 'const initialView = (location.hash || "#evtBoard").slice(1)' in js
    assert "function setContextPanel" in js


def test_work_board_dashboard_has_required_product_sections(app_env) -> None:
    html, css, js = _work_assets(app_env)

    board_start = html.index('data-view="evtBoard"')
    idea_start = html.index('data-view="idea"')
    board_html = html[board_start:idea_start]

    assert "事项看板" in board_html
    assert "统一查看待办、DDL、灵感和提醒路由" in board_html
    for item in ("今日待办", "即将截止", "灵感 Inbox", "设备状态"):
        assert item in board_html
    assert 'id="summaryTodayTodo"' in board_html
    assert 'id="summaryDeadline48h"' in board_html
    assert 'id="summaryIdeaInbox"' in board_html
    assert 'id="summaryDeviceState"' in board_html
    assert 'id="todayTaskList"' in board_html
    assert 'id="deadlineTimeline"' in board_html
    assert 'id="boardIdeaList"' in board_html
    assert 'id="notifyRoutePanel"' in board_html

    assert ".summary-grid" in css
    assert "grid-template-columns: repeat(4" in css
    assert ".task-row" in css
    assert ".deadline-timeline" in css
    assert ".route-row" in css

    for fn in (
        "renderSummary",
        "renderTodoList",
        "renderDeadlineTimeline",
        "renderBoardIdeaInbox",
        "renderNotifyRoute",
    ):
        assert f"function {fn}" in js


def test_work_add_event_has_natural_language_preview_and_templates(app_env) -> None:
    html, css, js = _work_assets(app_env)

    add_start = html.index('data-view="evtAdd"')
    board_start = html.index('data-view="evtBoard"')
    add_html = html[add_start:board_start]

    assert "一句话录入" in add_html
    assert 'id="naturalInput"' in add_html
    assert "解析并预填" in add_html
    assert "事件表单" in add_html
    for tab in ("普通事项", "截止事项", "课程", "灵感"):
        assert tab in add_html
    assert 'id="createPreview"' in add_html
    assert "创建前预览" in add_html
    assert "常用模板" in add_html
    for template in ("作业DDL", "生活提醒", "考试复习", "项目跟进"):
        assert template in add_html

    assert ".natural-input-card" in css
    assert ".form-tabs" in css
    assert ".create-preview" in css
    assert ".template-grid" in css

    for fn in (
        "parseNaturalInput",
        "prefillCreateForm",
        "renderCreatePreview",
        "applyTemplate",
        "setCreateTab",
    ):
        assert f"function {fn}" in js


def test_work_idea_device_and_log_views_match_inbox_workflow(app_env) -> None:
    html, css, js = _work_assets(app_env)

    assert "灵感中心" in html
    assert "沉淀想法、追踪设备状态、保留操作日志" in html
    assert 'id="ideaStatusFilter"' in html
    assert "open" in html
    assert "handled" in html
    assert "archived" in html
    assert "转事项" in html
    assert "转 DDL" in html
    assert "归档" in html

    assert 'id="devStatusFilter"' in html
    assert "状态时间线" in html
    assert "全部状态" in html
    assert 'id="deviceSummaryCard"' in html

    assert 'id="logKeyword"' in html
    assert 'id="logStatusFilter"' in html
    assert 'id="notifyLogPanel"' in html
    assert 'id="msgLogPanel"' in html
    assert 'id="actLogPanel"' in html

    assert ".inbox-list" in css
    assert ".device-timeline" in css
    assert ".log-row" in css

    for fn in (
        "renderIdeaInbox",
        "setIdeaFilter",
        "archiveIdea",
        "ideaToDdl",
        "renderDeviceStatus",
        "renderLogs",
        "filterLogs",
    ):
        assert f"function {fn}" in js


def test_work_redesign_preserves_existing_create_and_event_actions(app_env) -> None:
    html, _, js = _work_assets(app_env)

    for form_id in ("lifeEvtForm", "ddlEvtForm", "ideaForm", "courseTplForm", "courseInstForm"):
        assert f'id="{form_id}"' in html

    for action in (
        "openEvtDetail",
        "saveEvtDetail",
        "completeEvtDetail",
        "cancelEvtDetail",
        "completeEvt",
        "cancelEvt",
        "reopenEvt",
        "ideaToEvt",
    ):
        assert action in js

    assert "bindQuickForm(\"lifeEvtForm\"" in js
    assert "bindQuickForm(\"ddlEvtForm\"" in js
    assert "/api/lifeEvt" in html
    assert "/api/ddlEvt" in html
    assert "/api/idea" in html
