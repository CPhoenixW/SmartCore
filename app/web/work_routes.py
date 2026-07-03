# ruff: noqa: E501
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["work"])


@router.get("/work", response_class=HTMLResponse)
def workPage() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SmartCore Work</title>
<style>
:root {
  --bg: #0f1419;
  --surface: #1a2332;
  --surface2: #243044;
  --border: #2d3a4f;
  --text: #e8edf4;
  --muted: #8b9cb3;
  --accent: #3b82f6;
  --accent-hover: #2563eb;
  --success: #22c55e;
  --warn: #f59e0b;
  --danger: #ef4444;
  --prio-high: #f87171;
  --prio-mid: #fbbf24;
  --prio-low: #94a3b8;
  --radius: 8px;
  --shadow: 0 2px 8px rgba(0,0,0,.35);
}
*, *::before, *::after { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
  min-height: 100vh;
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 10;
}
header h1 { margin: 0; font-size: 1.25rem; font-weight: 600; }
header .meta { color: var(--muted); font-size: .85rem; }
.layout {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 1rem;
  padding: 1rem;
  max-width: 1400px;
  margin: 0 auto;
}
@media (max-width: 960px) {
  .layout { grid-template-columns: 1fr; }
}
main { display: flex; flex-direction: column; gap: 1rem; }
aside { display: flex; flex-direction: column; gap: 1rem; }
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow: hidden;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: .65rem 1rem;
  background: var(--surface2);
  border-bottom: 1px solid var(--border);
  font-weight: 600;
  font-size: .9rem;
}
.panel-body { padding: .75rem 1rem; }
.btn {
  border: none;
  border-radius: 6px;
  padding: .35rem .65rem;
  font-size: .8rem;
  cursor: pointer;
  background: var(--surface2);
  color: var(--text);
  border: 1px solid var(--border);
}
.btn:hover { background: var(--border); }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-success { background: var(--success); border-color: var(--success); color: #fff; }
.btn-danger { background: var(--danger); border-color: var(--danger); color: #fff; }
.btn-sm { padding: .2rem .45rem; font-size: .75rem; }
.quick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: .75rem;
}
.quick-form label {
  display: block;
  font-size: .75rem;
  color: var(--muted);
  margin-bottom: .2rem;
}
.quick-form input, .quick-form select, .quick-form textarea {
  width: 100%;
  padding: .4rem .5rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--text);
  font-size: .85rem;
  margin-bottom: .5rem;
}
.quick-form textarea { min-height: 52px; resize: vertical; }
.evt-columns {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: .75rem;
}
@media (max-width: 720px) {
  .evt-columns { grid-template-columns: 1fr; }
}
.evt-col { min-height: 120px; }
.evt-col-head {
  font-size: .8rem;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .04em;
  margin-bottom: .5rem;
  padding-bottom: .35rem;
  border-bottom: 1px solid var(--border);
}
.evt-col-head .count {
  display: inline-block;
  background: var(--surface2);
  border-radius: 999px;
  padding: 0 .45rem;
  margin-left: .35rem;
  font-size: .7rem;
}
.evt-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: .6rem .75rem;
  margin-bottom: .5rem;
  font-size: .85rem;
}
.evt-card .title { font-weight: 600; margin-bottom: .25rem; word-break: break-word; }
.evt-card .meta-line { color: var(--muted); font-size: .75rem; margin-bottom: .4rem; }
.evt-card .tag {
  display: inline-block;
  font-size: .65rem;
  padding: .1rem .35rem;
  border-radius: 4px;
  background: var(--surface2);
  margin-right: .25rem;
}
.evt-card .tag.prio-high { color: var(--prio-high); border: 1px solid var(--prio-high); }
.evt-card .tag.prio-mid { color: var(--prio-mid); border: 1px solid var(--prio-mid); }
.evt-card .tag.prio-low { color: var(--prio-low); border: 1px solid var(--prio-low); }
.evt-actions {
  display: flex;
  flex-wrap: wrap;
  gap: .35rem;
  align-items: center;
  margin-top: .4rem;
}
.evt-actions select {
  padding: .15rem .3rem;
  font-size: .75rem;
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
}
.log-list { max-height: 220px; overflow-y: auto; font-size: .78rem; }
.log-item {
  padding: .4rem 0;
  border-bottom: 1px solid var(--border);
}
.log-item:last-child { border-bottom: none; }
.log-item .log-title { font-weight: 500; }
.log-item .log-meta { color: var(--muted); font-size: .72rem; }
.empty { color: var(--muted); font-size: .82rem; font-style: italic; }
.dev-badge {
  display: inline-block;
  padding: .25rem .6rem;
  border-radius: 999px;
  font-size: .85rem;
  font-weight: 600;
  background: var(--surface2);
}
.dev-badge.working { background: #14532d; color: #86efac; }
.dev-badge.away { background: #713f12; color: #fde68a; }
.dev-badge.offline { background: #374151; color: #9ca3af; }
.flash {
  position: fixed;
  bottom: 1rem;
  right: 1rem;
  padding: .6rem 1rem;
  border-radius: var(--radius);
  background: var(--surface2);
  border: 1px solid var(--border);
  font-size: .85rem;
  opacity: 0;
  transition: opacity .25s;
  pointer-events: none;
  z-index: 100;
}
.flash.show { opacity: 1; }
</style>
</head>
<body>
<header>
  <h1>SmartCore 工作台</h1>
  <span class="meta" id="lastRefresh">—</span>
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
          <input id="lifeTitle" name="title" required placeholder="生活事项">
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
          <input id="ddlTitle" name="title" required placeholder="截止日期事项">
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
      <button type="button" class="btn btn-sm" id="refreshEvtBtn" data-action="refreshEvt">刷新</button>
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
  <section class="panel" id="notifyLogPanel">
    <div class="panel-head">
      <span>notifyLog</span>
      <button type="button" class="btn btn-sm" id="refreshNotifyBtn" data-action="refreshNotify">刷新</button>
    </div>
    <div class="panel-body"><div id="notifyLogList" class="log-list"></div></div>
  </section>
  <section class="panel" id="msgLogPanel">
    <div class="panel-head">
      <span>msgLog</span>
      <button type="button" class="btn btn-sm" id="refreshMsgBtn" data-action="refreshMsg">刷新</button>
    </div>
    <div class="panel-body"><div id="msgLogList" class="log-list"></div></div>
  </section>
  <section class="panel" id="actLogPanel">
    <div class="panel-head">
      <span>actLog</span>
      <button type="button" class="btn btn-sm" id="refreshActBtn" data-action="refreshAct">刷新</button>
    </div>
    <div class="panel-body"><div id="actLogList" class="log-list"></div></div>
  </section>
</aside>
</div>
<div class="flash" id="flash"></div>
<script>
(function () {
  const api = (path, opts) => fetch(path, opts).then(r => r.json());

  function showFlash(msg) {
    const el = document.getElementById("flash");
    el.textContent = msg;
    el.classList.add("show");
    setTimeout(() => el.classList.remove("show"), 2200);
  }

  function fmtDtLocal(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return d.toLocaleString("zh-CN", { hour12: false });
    } catch { return iso; }
  }

  function toIsoFromLocal(val) {
    if (!val) return null;
    const d = new Date(val);
    if (Number.isNaN(d.getTime())) return null;
    const pad = n => String(n).padStart(2, "0");
    const off = -d.getTimezoneOffset();
    const sign = off >= 0 ? "+" : "-";
    const abs = Math.abs(off);
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T` +
      `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}` +
      `${sign}${pad(Math.floor(abs/60))}:${pad(abs%60)}`;
  }

  function prioTag(prio) {
    return `<span class="tag prio-${prio}">${prio}</span>`;
  }

  function renderEvtCard(evt) {
    const extra = evt.evtType === "life"
      ? `due ${fmtDtLocal(evt.dueAt)}`
      : evt.evtType === "ddl"
        ? `ddl ${fmtDtLocal(evt.ddlAt)}${evt.hardDdl ? " · hard" : ""}`
        : `course ${evt.classDate || "—"}`;
    const prioSel = `<select data-evt-id="${evt.evtId}" data-action="setPrio">
      <option value="high"${evt.prio==="high"?" selected":""}>high</option>
      <option value="mid"${evt.prio==="mid"?" selected":""}>mid</option>
      <option value="low"${evt.prio==="low"?" selected":""}>low</option>
    </select>`;
    let actions = "";
    if (evt.stat === "todo") {
      actions = `<button class="btn btn-sm btn-success" data-action="completeEvt" data-evt-id="${evt.evtId}">完成</button>
        <button class="btn btn-sm btn-danger" data-action="cancelEvt" data-evt-id="${evt.evtId}">取消</button>`;
    }
    return `<div class="evt-card" data-evt-id="${evt.evtId}">
      <div class="title">${escapeHtml(evt.title)}</div>
      <div class="meta-line">
        <span class="tag">${evt.evtType}</span>${prioTag(evt.prio)} ${extra}
      </div>
      <div class="evt-actions">${prioSel}${actions}</div>
    </div>`;
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  }

  async function loadEvts() {
    const resp = await api("/api/evt");
    const evts = resp.data || [];
    const groups = { todo: [], done: [], cancelled: [] };
    evts.forEach(e => {
      if (groups[e.stat]) groups[e.stat].push(e);
    });
    ["todo","done","cancelled"].forEach(stat => {
      const listEl = document.getElementById("evtList" + stat.charAt(0).toUpperCase() + stat.slice(1));
      const countEl = document.getElementById(stat + "Count");
      const items = groups[stat];
      countEl.textContent = items.length;
      listEl.innerHTML = items.length
        ? items.map(renderEvtCard).join("")
        : '<span class="empty">无</span>';
    });
    touchRefresh();
  }

  async function loadIdeas() {
    const resp = await api("/api/idea");
    const ideas = resp.data || [];
    const el = document.getElementById("ideaList");
    el.innerHTML = ideas.length
      ? ideas.map(i => `<div class="log-item">
          <div class="log-title">${escapeHtml(i.content)}</div>
          <div class="log-meta">${i.handled ? "handled" : "open"} · ${fmtDtLocal(i.createdAt)}</div>
        </div>`).join("")
      : '<span class="empty">无</span>';
  }

  async function loadDevState() {
    const resp = await api("/api/devState");
    const rows = resp.data || [];
    const el = document.getElementById("devStateBody");
    if (!rows.length) {
      el.innerHTML = '<span class="empty">暂无设备上报</span>';
      return;
    }
    const latest = rows[0];
    const cls = ["working","away","offline"].includes(latest.state) ? latest.state : "";
    el.innerHTML = `<div><span class="dev-badge ${cls}">${escapeHtml(latest.state)}</span></div>
      <div class="log-meta" style="margin-top:.5rem">
        devId: ${escapeHtml(latest.devId)}<br>
        confidence: ${latest.confidence ?? "—"}<br>
        seenAt: ${fmtDtLocal(latest.seenAt)}
      </div>`;
  }

  function renderLogList(elId, rows, renderFn) {
    const el = document.getElementById(elId);
    el.innerHTML = rows.length
      ? rows.slice().reverse().slice(0, 40).map(renderFn).join("")
      : '<span class="empty">无</span>';
  }

  async function loadNotifyLog() {
    const resp = await api("/api/notifyLog");
    renderLogList("notifyLogList", resp.data || [], r =>
      `<div class="log-item"><div class="log-title">${escapeHtml(r.title)}</div>
       <div class="log-meta">${r.stat} · ${escapeHtml(r.channel)} · ${fmtDtLocal(r.scheduledAt)}</div></div>`);
  }

  async function loadMsgLog() {
    const resp = await api("/api/msgLog");
    renderLogList("msgLogList", resp.data || [], r =>
      `<div class="log-item"><div class="log-title">${escapeHtml(r.rawText || "—")}</div>
       <div class="log-meta">${r.src} · ${r.stat || "—"} · ${fmtDtLocal(r.createdAt)}</div></div>`);
  }

  async function loadActLog() {
    const resp = await api("/api/actLog");
    renderLogList("actLogList", resp.data || [], r =>
      `<div class="log-item"><div class="log-title">${escapeHtml(r.actType)} → ${escapeHtml(r.targetKind || "")}</div>
       <div class="log-meta">${r.src} · ${fmtDtLocal(r.createdAt)}</div></div>`);
  }

  function touchRefresh() {
    document.getElementById("lastRefresh").textContent =
      "更新于 " + new Date().toLocaleTimeString("zh-CN", { hour12: false });
  }

  async function refreshAll() {
    await Promise.all([
      loadEvts(), loadIdeas(), loadDevState(),
      loadNotifyLog(), loadMsgLog(), loadActLog()
    ]);
  }

  async function patchEvt(evtId, body) {
    const resp = await api(`/api/evt/${evtId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error("patch failed");
    return resp.data;
  }

  async function completeEvt(evtId) {
    await patchEvt(evtId, { stat: "done" });
    showFlash("已标记完成");
    await loadEvts();
    await loadActLog();
  }

  async function cancelEvt(evtId) {
    await api(`/api/evt/${evtId}`, { method: "DELETE" });
    showFlash("已取消");
    await loadEvts();
    await loadActLog();
  }

  async function setPrio(evtId, prio) {
    await patchEvt(evtId, { prio });
    showFlash("优先级已更新");
    await loadEvts();
  }

  function bindQuickForm(formId, buildBody) {
    document.getElementById(formId).addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const form = ev.target;
      const endpoint = form.dataset.endpoint;
      const body = buildBody(form);
      const resp = await api(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (resp.ok) {
        form.reset();
        showFlash("创建成功");
        await refreshAll();
      }
    });
  }

  bindQuickForm("lifeEvtForm", form => ({
    title: form.title.value.trim(),
    dueAt: toIsoFromLocal(form.dueAt.value),
    prio: form.prio.value,
  }));

  bindQuickForm("ddlEvtForm", form => ({
    title: form.title.value.trim(),
    ddlAt: toIsoFromLocal(form.ddlAt.value),
    hardDdl: form.hardDdl.checked,
    prio: form.prio.value,
  }));

  bindQuickForm("ideaForm", form => ({
    content: form.content.value.trim(),
    srcType: "text",
  }));

  document.body.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-action]");
    if (!btn) return;
    const action = btn.dataset.action;
    if (action === "refreshEvt") await loadEvts();
    else if (action === "refreshIdea") await loadIdeas();
    else if (action === "refreshDev") await loadDevState();
    else if (action === "refreshNotify") await loadNotifyLog();
    else if (action === "refreshMsg") await loadMsgLog();
    else if (action === "refreshAct") await loadActLog();
    else if (action === "completeEvt") await completeEvt(btn.dataset.evtId);
    else if (action === "cancelEvt") await cancelEvt(btn.dataset.evtId);
  });

  document.body.addEventListener("change", async (ev) => {
    const sel = ev.target.closest('[data-action="setPrio"]');
    if (!sel) return;
    await setPrio(sel.dataset.evtId, sel.value);
  });

  refreshAll();
})();
</script>
</body>
</html>"""
