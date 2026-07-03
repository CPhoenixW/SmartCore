const apiStatusEl = document.getElementById("apiStatus");
const lastRefreshEl = document.getElementById("lastRefresh");
const liveDotEl = document.getElementById("liveDot");
const flashEl = document.getElementById("flash");
const evtSearchEl = document.getElementById("evtSearch");
const DEV_REFRESH_MS = 15000;
const VIEW_REFRESH_MS = 30000;
let evtCache = [];
let tplCache = [];

function $(id) { return document.getElementById(id); }

function setApiStatus(state, label) {
  apiStatusEl.className = `status-pill ${state}`;
  apiStatusEl.textContent = label;
}

async function api(path, opts) {
  setApiStatus("busy", "API …");
  try {
    const resp = await fetch(path, opts);
    const data = await resp.json();
    setApiStatus(resp.ok ? "ok" : "err", resp.ok ? "API 在线" : `API ${resp.status}`);
    return { ok: resp.ok, ...data };
  } catch {
    setApiStatus("err", "API 离线");
    return { ok: false, data: null };
  }
}

function showFlash(msg) {
  flashEl.textContent = msg;
  flashEl.classList.add("show");
  setTimeout(() => flashEl.classList.remove("show"), 2200);
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtDtLocal(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("zh-CN", { hour12: false }); } catch { return iso; }
}

function toIsoFromLocal(val) {
  if (!val) return null;
  const d = new Date(val);
  if (Number.isNaN(d.getTime())) return null;
  const pad = (n) => String(n).padStart(2, "0");
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const abs = Math.abs(off);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:00${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

function touchRefresh() {
  lastRefreshEl.textContent = "更新于 " + new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

function setLivePulse(on) {
  liveDotEl?.classList.toggle("pulse", on);
}

function activeView(name) {
  document.querySelectorAll("[data-view-tab]").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.viewTab === name);
  });
  document.querySelectorAll("[data-view]").forEach((view) => {
    view.classList.toggle("active", view.dataset.view === name);
  });
  location.hash = name;
}

function getActiveViewName() {
  return document.querySelector("[data-view].active")?.dataset.view || "evtAdd";
}

function isUserTyping() {
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return Boolean(el.isContentEditable);
}

function evtExtra(evt) {
  if (evt.evtType === "life") return `due ${fmtDtLocal(evt.dueAt)}`;
  if (evt.evtType === "ddl") return `ddl ${fmtDtLocal(evt.ddlAt)}${evt.hardDdl ? " · hard" : ""}`;
  return `course ${evt.classDate || "—"}`;
}

function renderEvtCard(evt) {
  return `<div class="evt-card" data-evt-id="${evt.evtId}" data-search="${escapeHtml(`${evt.title} ${evt.desc || ""} ${evt.evtType} ${evt.prio} ${evt.stat}`.toLowerCase())}">
    <div class="title-row">
      <input class="inline-title" data-action="fieldEdit" data-field="title" data-evt-id="${evt.evtId}" value="${escapeHtml(evt.title)}">
      <select data-action="fieldEdit" data-field="stat" data-evt-id="${evt.evtId}">
        ${["todo", "done", "cancelled"].map((s) => `<option value="${s}"${evt.stat === s ? " selected" : ""}>${s}</option>`).join("")}
      </select>
    </div>
    <textarea class="inline-desc" data-action="fieldEdit" data-field="desc" data-evt-id="${evt.evtId}" placeholder="描述">${escapeHtml(evt.desc || "")}</textarea>
    <div class="meta-line"><span class="tag">${evt.evtType}</span><span class="tag prio-${evt.prio}">${evt.prio}</span> ${evtExtra(evt)}</div>
    <div class="evt-actions">
      <select data-action="fieldEdit" data-field="prio" data-evt-id="${evt.evtId}">
        ${["high", "mid", "low"].map((p) => `<option value="${p}"${evt.prio === p ? " selected" : ""}>${p}</option>`).join("")}
      </select>
      <button type="button" class="btn btn-sm btn-success" data-action="completeEvt" data-evt-id="${evt.evtId}">完成</button>
      <button type="button" class="btn btn-sm btn-danger" data-action="cancelEvt" data-evt-id="${evt.evtId}">取消</button>
    </div>
  </div>`;
}

function applyEvtSearch() {
  const q = (evtSearchEl?.value || "").trim().toLowerCase();
  document.querySelectorAll(".evt-card").forEach((card) => {
    card.classList.toggle("hidden-by-search", q && !(card.dataset.search || "").includes(q));
  });
}

function renderEvtBoard(evts) {
  evtCache = evts;
  const groups = { todo: [], done: [], cancelled: [] };
  evts.forEach((e) => { (groups[e.stat] || groups.todo).push(e); });
  for (const stat of ["todo", "done", "cancelled"]) {
    const id = stat.charAt(0).toUpperCase() + stat.slice(1);
    $(`evtList${id}`).innerHTML = groups[stat].length ? groups[stat].map(renderEvtCard).join("") : '<span class="empty">无</span>';
    $(`${stat}Count`).textContent = groups[stat].length;
  }
  applyEvtSearch();
}

async function loadEvts() {
  const resp = await api("/api/evt");
  renderEvtBoard(resp.data || []);
  touchRefresh();
}

async function patchEvt(evtId, body) {
  const resp = await api(`/api/evt/${evtId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (resp.ok) showFlash("已更新");
  await loadEvts();
  await loadActLog();
}

async function loadIdeas() {
  const resp = await api("/api/idea");
  const ideas = resp.data || [];
  $("ideaList").innerHTML = ideas.length ? ideas.map((i) => `<div class="list-card">
    <div class="list-title">${escapeHtml(i.content)}</div>
    <div class="log-meta">${i.handled ? "handled" : "open"} · ${fmtDtLocal(i.createdAt)}</div>
    <div class="evt-actions">
      <input placeholder="转换标题" data-idea-title="${i.ideaId}" value="${escapeHtml(i.content.slice(0, 24))}">
      <button class="btn btn-sm btn-primary" data-action="ideaToEvt" data-idea-id="${i.ideaId}">转 lifeEvt</button>
    </div>
  </div>`).join("") : '<span class="empty">无</span>';
}

async function loadCourses() {
  const [tplResp, instResp] = await Promise.all([api("/api/courseTpl"), api("/api/courseInst")]);
  tplCache = tplResp.data || [];
  $("courseTplList").innerHTML = tplCache.length ? tplCache.map((t) => `<div class="list-card"><div class="list-title">${escapeHtml(t.courseName)}</div><div class="log-meta">${escapeHtml(t.tplId)} · 周${t.weekday} · ${escapeHtml(t.room || "")}</div></div>`).join("") : '<span class="empty">无</span>';
  $("courseInstList").innerHTML = (instResp.data || []).length ? instResp.data.map((c) => `<div class="list-card"><div class="list-title">${escapeHtml(c.title)}</div><div class="log-meta">${escapeHtml(c.tplId)} · ${escapeHtml(c.classDate || "—")} · ${escapeHtml(c.attendStat)}</div></div>`).join("") : '<span class="empty">无</span>';
}

const WORK_STATE_LABELS = {
  working: "工作中",
  away: "离开",
  offline: "离线",
  unknown: "未知",
};

function pickPrimaryDevState(rows) {
  if (!rows?.length) return null;
  const pi = rows.find((r) => r.devId === "pi");
  return pi || rows[0];
}

function formatStateAge(seenAt) {
  if (!seenAt) return "—";
  try {
    const diff = Date.now() - new Date(seenAt).getTime();
    if (diff < 60_000) return "刚刚";
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
    return fmtDtLocal(seenAt);
  } catch {
    return "—";
  }
}

function renderPrimaryDevState(row) {
  const root = $("currentWorkState");
  const labelEl = $("workStateLabel");
  const sourceEl = $("workStateSource");
  const ageEl = $("workStateAge");
  if (!root || !labelEl || !sourceEl || !ageEl) return;
  const state = row?.state || "unknown";
  root.dataset.state = state;
  labelEl.textContent = WORK_STATE_LABELS[state] || state;
  sourceEl.textContent = row ? `来源 ${row.devId}` : "暂无设备";
  ageEl.textContent = row ? formatStateAge(row.seenAt) : "—";
}

function updateWorkPresence(row) {
  renderPrimaryDevState(row);
}

function renderDevStateList(rows) {
  $("devStateBody").innerHTML = rows.length ? rows.slice(0, 24).map((r) => {
    const meta = r.meta && typeof r.meta === "object" ? r.meta : {};
    return `<div class="list-card"><span class="dev-badge ${escapeHtml(r.state)}">${escapeHtml(r.state)}</span><div class="log-meta">devId: ${escapeHtml(r.devId)} · confidence: ${r.confidence ?? "—"} · ${fmtDtLocal(r.seenAt)}<br>${escapeHtml(meta.rawStatus || "")} ${escapeHtml(meta.identity || "")}</div></div>`;
  }).join("") : '<span class="empty">暂无设备上报</span>';
}

async function loadDevState() {
  const resp = await api("/api/devState");
  const rows = resp.data || [];
  renderDevStateList(rows);
  const primary = pickPrimaryDevState(rows);
  renderPrimaryDevState(primary);
  updateWorkPresence(primary);
}

function renderLogList(elId, rows, renderFn) {
  $(elId).innerHTML = rows.length ? rows.slice().reverse().slice(0, 60).map(renderFn).join("") : '<span class="empty">无</span>';
}

async function loadNotifyLog() {
  const resp = await api("/api/notifyLog");
  renderLogList("notifyLogList", resp.data || [], (r) => `<div class="list-card"><div class="list-title">${escapeHtml(r.title)}</div><div class="log-meta">${escapeHtml(r.stat)} · ${escapeHtml(r.channel || r.targetKind || "")} · ${fmtDtLocal(r.scheduledAt)}</div></div>`);
}

async function loadMsgLog() {
  const resp = await api("/api/msgLog");
  renderLogList("msgLogList", resp.data || [], (r) => `<div class="list-card"><div class="list-title">${escapeHtml(r.rawText || "—")}</div><div class="log-meta">${escapeHtml(r.src)} · ${escapeHtml(r.stat || "—")} · ${fmtDtLocal(r.createdAt)}</div></div>`);
}

async function loadActLog() {
  const resp = await api("/api/actLog");
  renderLogList("actLogList", resp.data || [], (r) => `<div class="list-card"><div class="list-title">${escapeHtml(r.actType)} → ${escapeHtml(r.targetKind || "")}</div><div class="log-meta">${escapeHtml(r.src)} · ${fmtDtLocal(r.createdAt)}</div>${r.undoToken ? `<button class="btn btn-sm" data-action="undoAct" data-undo-token="${escapeHtml(r.undoToken)}">undo</button>` : ""}</div>`);
}

async function refreshAll() {
  setLivePulse(true);
  try {
    await Promise.all([loadEvts(), loadIdeas(), loadCourses(), loadDevState(), loadNotifyLog(), loadMsgLog(), loadActLog()]);
  } finally {
    setLivePulse(false);
  }
}

async function refreshActiveView() {
  if (isUserTyping()) return;
  const view = getActiveViewName();
  setLivePulse(true);
  try {
    if (view === "evtAdd" || view === "evtBoard") await loadEvts();
    else if (view === "idea") await loadIdeas();
    else if (view === "course") await loadCourses();
    else if (view === "dev") await loadDevState();
    else if (view === "log") {
      const logTab = document.querySelector(".log-tab.active")?.dataset.logTab;
      if (logTab === "msg") await loadMsgLog();
      else if (logTab === "act") await loadActLog();
      else await loadNotifyLog();
    }
  } finally {
    setLivePulse(false);
  }
}

async function refreshDevStatePeriodic() {
  setLivePulse(true);
  try {
    await loadDevState();
  } finally {
    setLivePulse(false);
  }
}

function formVal(form, name) { return form.elements[name]?.value?.trim() || ""; }
function numOrNull(v) { return v ? Number(v) : null; }

function bindQuickForm(formId, buildBody, after) {
  const form = $(formId);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const resp = await api(form.dataset.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildBody(form)),
    });
    if (resp.ok) {
      form.reset();
      showFlash("创建成功");
      await (after || refreshAll)();
    }
  });
}

bindQuickForm("lifeEvtForm", (f) => ({ title: formVal(f, "title"), desc: formVal(f, "desc") || null, dueAt: toIsoFromLocal(formVal(f, "dueAt")), prio: formVal(f, "prio") }), loadEvts);
bindQuickForm("ddlEvtForm", (f) => ({ title: formVal(f, "title"), desc: formVal(f, "desc") || null, ddlAt: toIsoFromLocal(formVal(f, "ddlAt")), hardDdl: f.elements.hardDdl.checked, prio: formVal(f, "prio") }), loadEvts);
bindQuickForm("ideaForm", (f) => ({ content: formVal(f, "content"), srcType: "text" }), loadIdeas);
bindQuickForm("courseTplForm", (f) => ({ courseName: formVal(f, "courseName"), teacher: formVal(f, "teacher") || null, room: formVal(f, "room") || null, weekday: Number(formVal(f, "weekday")), startTime: formVal(f, "startTime") || null, endTime: formVal(f, "endTime") || null, startWeek: numOrNull(formVal(f, "startWeek")), endWeek: numOrNull(formVal(f, "endWeek")), weekMode: formVal(f, "weekMode"), semester: formVal(f, "semester") || null }), loadCourses);
bindQuickForm("courseInstForm", (f) => ({ title: formVal(f, "title"), tplId: formVal(f, "tplId"), classDate: formVal(f, "classDate") || null, attendStat: formVal(f, "attendStat") }), loadCourses);

document.body.addEventListener("click", async (ev) => {
  const tab = ev.target.closest("[data-view-tab]");
  if (tab) return activeView(tab.dataset.viewTab);
  const btn = ev.target.closest("[data-action]");
  if (!btn) return;
  const a = btn.dataset.action;
  if (a === "refreshAll") await refreshAll();
  else if (a === "refreshEvt") await loadEvts();
  else if (a === "refreshIdea") await loadIdeas();
  else if (a === "refreshCourse") await loadCourses();
  else if (a === "refreshDev") await loadDevState();
  else if (a === "refreshNotify") await loadNotifyLog();
  else if (a === "refreshMsg") await loadMsgLog();
  else if (a === "refreshAct") await loadActLog();
  else if (a === "completeEvt") await patchEvt(btn.dataset.evtId, { stat: "done" });
  else if (a === "cancelEvt") await api(`/api/evt/${btn.dataset.evtId}`, { method: "DELETE" }).then(loadEvts);
  else if (a === "ideaToEvt") {
    const title = document.querySelector(`[data-idea-title="${btn.dataset.ideaId}"]`)?.value || "灵感事项";
    await api(`/api/idea/${btn.dataset.ideaId}/toEvt`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, dueAt: null }) });
    await Promise.all([loadIdeas(), loadEvts(), loadActLog()]);
  } else if (a === "undoAct") {
    await api(`/api/undo/${btn.dataset.undoToken}`, { method: "POST" });
    await refreshAll();
  }
});

document.body.addEventListener("change", async (ev) => {
  const el = ev.target.closest('[data-action="fieldEdit"]');
  if (!el) return;
  await patchEvt(el.dataset.evtId, { [el.dataset.field]: el.value });
});

document.body.addEventListener("blur", async (ev) => {
  const el = ev.target.closest('input[data-action="fieldEdit"], textarea[data-action="fieldEdit"]');
  if (!el) return;
  const evt = evtCache.find((e) => e.evtId === el.dataset.evtId);
  if (!evt || String(evt[el.dataset.field] || "") === el.value) return;
  await patchEvt(el.dataset.evtId, { [el.dataset.field]: el.value });
}, true);

document.querySelectorAll(".log-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".log-tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll(".log-pane").forEach((p) => p.classList.toggle("active", p.dataset.logPane === tab.dataset.logTab));
  });
});

evtSearchEl?.addEventListener("input", applyEvtSearch);

const initialView = (location.hash || "#evtAdd").slice(1);
activeView(["evtAdd", "evtBoard", "idea", "course", "dev", "log"].includes(initialView) ? initialView : "evtAdd");
refreshAll();
setInterval(refreshDevStatePeriodic, DEV_REFRESH_MS);
setInterval(refreshActiveView, VIEW_REFRESH_MS);
