const apiStatusEl = document.getElementById("apiStatus");
const lastRefreshEl = document.getElementById("lastRefresh");
const liveDotEl = document.getElementById("liveDot");
const flashEl = document.getElementById("flash");
const evtSearchEl = document.getElementById("evtSearch");
const globalSearchEl = document.getElementById("globalSearch");
const DEV_REFRESH_MS = 15000;
const VIEW_REFRESH_MS = 30000;
let evtCache = [];
let ideaCache = [];
let devCache = [];
let tplCache = [];
let activeEvtId = null;
let ideaFilter = "open";
let archivedIdeaIds = new Set(JSON.parse(localStorage.getItem("scArchivedIdeas") || "[]"));
let activeCreateTab = "life";
let notifyLogCache = [];
let msgLogCache = [];
let actLogCache = [];
let primaryDevState = null;

const EVT_TYPE_LABELS = { life: "生活", ddl: "截止", course: "课程" };
const EVT_STAT_LABELS = { todo: "待办", done: "完成", cancelled: "已取消" };
const EVT_PRIO_LABELS = { high: "高", mid: "中", low: "低" };

const CONTEXT_HINTS = {
  overview: "总览聚合各模块入口，适合快速跳转。",
  evtAdd: "添加事件支持自然语言预填，创建前请确认预览。",
  evtBoard: "事项看板展示今日待办与未来 48 小时 DDL。",
  idea: "灵感 Inbox：open 未处理，handled 已转事项，archived 已归档。",
  course: "维护课表模板与课程实例。",
  dev: "设备状态决定提醒路由：工位走副屏，离开走飞书。",
  log: "notify / msg / act 日志可按关键词与状态筛选。",
  settings: "工作台偏好设置。",
};

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

function getEvtTime(evt) {
  const raw = evt.evtType === "life" ? evt.dueAt : evt.evtType === "ddl" ? evt.ddlAt : evt.classDate;
  const prefix = evt.evtType === "life" ? "截止" : evt.evtType === "ddl" ? "DDL" : "上课";
  if (!raw) return { label: `${prefix} —`, overdue: false, dt: null };
  const dt = new Date(raw);
  if (Number.isNaN(dt.getTime())) return { label: `${prefix} ${raw}`, overdue: false, dt: null };
  const overdue = evt.stat === "todo" && evt.evtType !== "course" && dt.getTime() < Date.now();
  return { label: fmtBoardTime(dt, prefix, overdue), overdue, dt };
}

function isSameDay(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function fmtBoardTime(dt, prefix, overdue = false) {
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const dayText = isSameDay(dt, today)
    ? "今天"
    : isSameDay(dt, tomorrow)
      ? "明天"
      : isSameDay(dt, yesterday)
        ? "昨天"
        : `${dt.getMonth() + 1}月${dt.getDate()}日`;
  const timeText = dt.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${prefix} ${dayText} ${timeText}${overdue ? " · 已逾期" : ""}`;
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

function toLocalInputValue(iso, kind = "datetime") {
  if (!iso) return "";
  if (kind === "date") return String(iso).slice(0, 10);
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function touchRefresh() {
  lastRefreshEl.textContent = "更新于 " + new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

function setLivePulse(on) {
  liveDotEl?.classList.toggle("pulse", on);
}

function setContextPanel(view) {
  const body = $("contextBody");
  if (!body) return;
  body.textContent = CONTEXT_HINTS[view] || "选择视图以查看相关提示与快捷操作。";
}

function activeView(name) {
  document.querySelectorAll("[data-view-tab]").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.viewTab === name);
  });
  document.querySelectorAll("[data-view]").forEach((view) => {
    view.classList.toggle("active", view.dataset.view === name);
  });
  location.hash = name;
  setContextPanel(name);
}

function getActiveViewName() {
  return document.querySelector("[data-view].active")?.dataset.view || "evtBoard";
}

function isUserTyping() {
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return Boolean(el.isContentEditable);
}

function isEvtDetailOpen() {
  return $("evtDetailDrawer")?.classList.contains("open") ?? false;
}

function shortDesc(desc, max = 88) {
  if (!desc) return "";
  const text = String(desc).trim();
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function renderEvtActions(evt) {
  if (evt.stat === "todo") {
    return `<div class="board-card-actions" aria-label="事项操作">
      <button type="button" class="icon-btn success" data-action="completeEvt" data-evt-id="${evt.evtId}" title="完成" aria-label="完成">✓</button>
      <button type="button" class="icon-btn danger" data-action="cancelEvt" data-evt-id="${evt.evtId}" title="取消" aria-label="取消">×</button>
    </div>`;
  }
  if (evt.stat === "done" || evt.stat === "cancelled") {
    return `<div class="board-card-actions" aria-label="事项操作">
      <button type="button" class="icon-btn ghost" data-action="reopenEvt" data-evt-id="${evt.evtId}" title="恢复为待办" aria-label="恢复为待办">↺</button>
    </div>`;
  }
  return "";
}

function renderEvtCard(evt) {
  const desc = shortDesc(evt.desc);
  const time = getEvtTime(evt);
  const timeClass = time.overdue ? "board-card-time overdue" : "board-card-time";
  const ariaLabel = `打开事项：${evt.title}`;
  return `<article class="evt-card" role="button" data-action="openEvtDetail" data-evt-id="${evt.evtId}" tabindex="0" aria-label="${escapeHtml(ariaLabel)}" data-search="${escapeHtml(`${evt.title} ${evt.desc || ""} ${time.label} ${evt.evtType} ${evt.prio} ${evt.stat}`.toLowerCase())}">
    <div class="board-card-main">
      <h4 class="board-card-title">${escapeHtml(evt.title)}</h4>
      <div class="board-card-meta">
        <span class="tag">${escapeHtml(EVT_TYPE_LABELS[evt.evtType] || evt.evtType)}</span>
        <span class="tag prio-${escapeHtml(evt.prio)}">${escapeHtml(EVT_PRIO_LABELS[evt.prio] || evt.prio)}</span>
      </div>
      ${desc ? `<p class="board-card-desc">${escapeHtml(desc)}</p>` : ""}
    </div>
    <footer class="board-card-footer">
      <span class="${timeClass}">${escapeHtml(time.label)}</span>
      ${renderEvtActions(evt)}
    </footer>
  </article>`;
}

function applyEvtSearch() {
  const q = (evtSearchEl?.value || globalSearchEl?.value || "").trim().toLowerCase();
  document.querySelectorAll(".evt-card, .task-row").forEach((card) => {
    card.classList.toggle("hidden-by-search", q && !(card.dataset.search || "").includes(q));
  });
}

function markActiveEvtCard(evtId) {
  document.querySelectorAll(".evt-card.active, .task-row.active").forEach((card) => card.classList.remove("active"));
  if (!evtId) return;
  document.querySelector(`.evt-card[data-evt-id="${evtId}"], .task-row[data-evt-id="${evtId}"]`)?.classList.add("active");
}

function isToday(dt) {
  if (!dt) return false;
  return isSameDay(dt, new Date());
}

function renderSummary(evts, ideas, devRow) {
  const todos = evts.filter((e) => e.stat === "todo");
  const todayTodos = todos.filter((e) => {
    const t = getEvtTime(e);
    return !t.dt || isToday(t.dt) || e.evtType === "life";
  });
  const now = Date.now();
  const in48h = todos.filter((e) => {
    const t = getEvtTime(e);
    if (!t.dt || e.evtType === "course") return false;
    const diff = t.dt.getTime() - now;
    return diff >= 0 && diff <= 48 * 3600_000;
  });
  const openIdeas = ideas.filter((i) => !i.handled && !archivedIdeaIds.has(i.ideaId));
  $("summaryTodayTodo").textContent = String(todayTodos.length);
  $("summaryDeadline48h").textContent = String(in48h.length);
  $("summaryIdeaInbox").textContent = String(openIdeas.length);
  const state = devRow?.state || "unknown";
  $("summaryDeviceState").textContent = WORK_STATE_LABELS[state] || state;
}

function renderTodoList(evts) {
  const el = $("todayTaskList");
  if (!el) return;
  const todos = evts.filter((e) => e.stat === "todo").slice(0, 12);
  el.innerHTML = todos.length
    ? todos.map((evt) => {
        const time = getEvtTime(evt);
        return `<div class="task-row" role="button" tabindex="0" data-action="openEvtDetail" data-evt-id="${evt.evtId}" data-search="${escapeHtml(`${evt.title} ${evt.desc || ""}`.toLowerCase())}">
          <span class="task-row-title">${escapeHtml(evt.title)}</span>
          <span class="task-row-meta">${escapeHtml(time.label)}</span>
        </div>`;
      }).join("")
    : '<span class="empty">今日暂无待办</span>';
  applyEvtSearch();
}

function renderDeadlineTimeline(evts) {
  const el = $("deadlineTimeline");
  if (!el) return;
  const now = Date.now();
  const items = evts
    .filter((e) => e.stat === "todo" && e.evtType !== "course")
    .map((e) => ({ evt: e, time: getEvtTime(e) }))
    .filter(({ time }) => time.dt && time.dt.getTime() >= now && time.dt.getTime() <= now + 48 * 3600_000)
    .sort((a, b) => a.time.dt - b.time.dt);
  el.innerHTML = items.length
    ? items.map(({ evt, time }) => `<div class="timeline-item">
        <span class="timeline-time">${escapeHtml(time.dt.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }))}</span>
        <span class="timeline-title">${escapeHtml(evt.title)}</span>
      </div>`).join("")
    : '<span class="empty">48 小时内无截止</span>';
}

function renderBoardIdeaInbox(ideas) {
  const el = $("boardIdeaList");
  if (!el) return;
  const open = ideas.filter((i) => !i.handled && !archivedIdeaIds.has(i.ideaId)).slice(-3).reverse();
  el.innerHTML = open.length
    ? open.map((i) => `<div class="idea-mini-item">${escapeHtml(shortDesc(i.content, 64))}</div>`).join("")
    : '<span class="empty">暂无 open 灵感</span>';
}

function renderNotifyRoute(devRow) {
  const el = $("notifyRoutePanel");
  if (!el) return;
  const state = devRow?.state || "unknown";
  const atDesk = state === "working";
  el.innerHTML = `
    <div class="route-row"><span class="route-label">工位状态</span><span class="route-value">${escapeHtml(WORK_STATE_LABELS[state] || state)}</span></div>
    <div class="route-row"><span class="route-label">副屏提醒</span><span class="route-value">${atDesk ? "启用" : "跳过"}</span></div>
    <div class="route-row"><span class="route-label">飞书提醒</span><span class="route-value">${atDesk ? "备用" : "启用"}</span></div>`;
}

function renderEvtBoard(evts) {
  evtCache = evts;
  const groups = { todo: [], done: [], cancelled: [] };
  evts.forEach((e) => { (groups[e.stat] || groups.todo).push(e); });
  for (const stat of ["done", "cancelled"]) {
    const id = stat.charAt(0).toUpperCase() + stat.slice(1);
    $(`evtList${id}`).innerHTML = groups[stat].length ? groups[stat].map(renderEvtCard).join("") : '<span class="empty">无</span>';
    $(`${stat}Count`).textContent = groups[stat].length;
  }
  $("todoCount").textContent = groups.todo.length;
  if ($("todoCountVisible")) $("todoCountVisible").textContent = groups.todo.length;
  const doneCount = groups.done.length;
  const cancelledCount = groups.cancelled.length;
  const todoCount = groups.todo.length;
  $("archiveCount").textContent = doneCount + cancelledCount;
  $("evtArchiveDetails").open = doneCount + cancelledCount > 0 && todoCount === 0;
  renderSummary(evts, ideaCache, primaryDevState);
  renderTodoList(evts);
  renderDeadlineTimeline(evts);
  renderBoardIdeaInbox(ideaCache);
  renderNotifyRoute(primaryDevState);
  applyEvtSearch();
  if (activeEvtId) markActiveEvtCard(activeEvtId);
}

function setCreateTab(tab) {
  activeCreateTab = tab;
  document.querySelectorAll("[data-create-tab]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.createTab === tab);
  });
  document.querySelectorAll("[data-create-pane]").forEach((pane) => {
    pane.classList.toggle("active", pane.dataset.createPane === tab);
  });
  renderCreatePreview();
}

function parseNaturalInput(text) {
  const raw = String(text || "").trim();
  const result = { tab: "life", title: "", desc: "", dueAt: "", prio: "mid", hardDdl: false };
  if (!raw) return result;
  result.title = raw.replace(/^(创建|添加|新建)\s*/u, "").slice(0, 120);
  if (/DDL|截止|deadline/i.test(raw)) result.tab = "ddl";
  if (/灵感|想法|idea/i.test(raw)) result.tab = "idea";
  if (/课程|上课|course/i.test(raw)) result.tab = "course";
  if (/高优先级|紧急|important/i.test(raw)) result.prio = "high";
  if (/低优先级|low/i.test(raw)) result.prio = "low";
  if (/硬性|hard/i.test(raw)) result.hardDdl = true;
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (/明天/u.test(raw)) result.dueAt = toLocalInputValue(tomorrow.toISOString());
  else if (/今天/u.test(raw)) result.dueAt = toLocalInputValue(new Date().toISOString());
  const timeMatch = raw.match(/(\d{1,2})[:：点时](\d{0,2})/u);
  if (timeMatch && result.dueAt) {
    const d = new Date(result.dueAt);
    d.setHours(Number(timeMatch[1]), Number(timeMatch[2] || 0), 0, 0);
    result.dueAt = toLocalInputValue(d.toISOString());
  }
  return result;
}

function prefillCreateForm(parsed) {
  setCreateTab(parsed.tab);
  if (parsed.tab === "life") {
    const f = $("lifeEvtForm");
    if (f) {
      f.elements.title.value = parsed.title;
      f.elements.desc.value = parsed.desc || "";
      if (parsed.dueAt) f.elements.dueAt.value = parsed.dueAt;
      f.elements.prio.value = parsed.prio;
    }
  } else if (parsed.tab === "ddl") {
    const f = $("ddlEvtForm");
    if (f) {
      f.elements.title.value = parsed.title;
      f.elements.desc.value = parsed.desc || "";
      if (parsed.dueAt) f.elements.ddlAt.value = parsed.dueAt;
      f.elements.prio.value = parsed.prio;
      f.elements.hardDdl.checked = parsed.hardDdl;
    }
  } else if (parsed.tab === "idea") {
    const f = $("ideaForm");
    if (f) f.elements.content.value = parsed.title;
  }
  renderCreatePreview();
}

function renderCreatePreview() {
  const body = $("createPreviewBody");
  if (!body) return;
  if (activeCreateTab === "life") {
    const f = $("lifeEvtForm");
    body.innerHTML = f ? `<div><strong>普通事项</strong> · ${escapeHtml(formVal(f, "title") || "—")}<br><span class="log-meta">优先级 ${escapeHtml(formVal(f, "prio"))} · ${escapeHtml(formVal(f, "dueAt") || "无截止")}</span></div>` : '<span class="empty">—</span>';
  } else if (activeCreateTab === "ddl") {
    const f = $("ddlEvtForm");
    body.innerHTML = f ? `<div><strong>截止事项</strong> · ${escapeHtml(formVal(f, "title") || "—")}<br><span class="log-meta">DDL ${escapeHtml(formVal(f, "ddlAt") || "—")} · hard ${$("ddlEvtForm")?.elements.hardDdl.checked ? "是" : "否"}</span></div>` : '<span class="empty">—</span>';
  } else if (activeCreateTab === "idea") {
    const f = $("ideaForm");
    body.innerHTML = f ? `<div><strong>灵感</strong> · ${escapeHtml(formVal(f, "content") || "—")}</div>` : '<span class="empty">—</span>';
  } else {
    body.innerHTML = '<span class="empty">课程表单请在课程标签填写</span>';
  }
}

function applyTemplate(name) {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  tomorrow.setHours(23, 59, 0, 0);
  const due = toLocalInputValue(tomorrow.toISOString());
  if (name === "homework") {
    setCreateTab("ddl");
    const f = $("ddlEvtForm");
    f.elements.title.value = "作业提交";
    f.elements.desc.value = "课程作业 DDL";
    f.elements.ddlAt.value = due;
    f.elements.prio.value = "high";
    f.elements.hardDdl.checked = true;
  } else if (name === "life") {
    setCreateTab("life");
    const f = $("lifeEvtForm");
    f.elements.title.value = "生活提醒";
    f.elements.desc.value = "";
    f.elements.dueAt.value = due;
    f.elements.prio.value = "mid";
  } else if (name === "exam") {
    setCreateTab("ddl");
    const f = $("ddlEvtForm");
    f.elements.title.value = "考试复习";
    f.elements.desc.value = "复习计划";
    f.elements.ddlAt.value = due;
    f.elements.prio.value = "high";
  } else if (name === "project") {
    setCreateTab("life");
    const f = $("lifeEvtForm");
    f.elements.title.value = "项目跟进";
    f.elements.desc.value = "阶段检查";
    f.elements.prio.value = "mid";
  }
  renderCreatePreview();
  showFlash("已应用模板");
}

function ideaStatusOf(idea) {
  if (archivedIdeaIds.has(idea.ideaId)) return "archived";
  return idea.handled ? "handled" : "open";
}

function setIdeaFilter(value) {
  ideaFilter = value;
  renderIdeaInbox(ideaCache);
}

function persistArchived() {
  localStorage.setItem("scArchivedIdeas", JSON.stringify([...archivedIdeaIds]));
}

function archiveIdea(ideaId) {
  archivedIdeaIds.add(ideaId);
  persistArchived();
  renderIdeaInbox(ideaCache);
  renderBoardIdeaInbox(ideaCache);
  renderSummary(evtCache, ideaCache, primaryDevState);
  showFlash("已归档");
}

async function ideaToDdl(ideaId) {
  const idea = ideaCache.find((i) => i.ideaId === ideaId);
  if (!idea) return;
  const title = idea.content.slice(0, 48) || "灵感 DDL";
  const resp = await api("/api/ddlEvt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, desc: idea.content, ddlAt: null, hardDdl: false, prio: "mid" }),
  });
  if (resp.ok) {
    archivedIdeaIds.add(ideaId);
    persistArchived();
    showFlash("已转为 DDL");
    await Promise.all([loadIdeas(), loadEvts(), loadActLog()]);
  }
}

function renderIdeaInbox(ideas) {
  ideaCache = ideas;
  const filtered = ideas.filter((i) => ideaStatusOf(i) === ideaFilter);
  $("ideaList").innerHTML = filtered.length
    ? filtered.map((i) => `<article class="inbox-item">
        <div class="list-title">${escapeHtml(i.content)}</div>
        <div class="log-meta">${ideaStatusOf(i)} · ${fmtDtLocal(i.createdAt)}</div>
        <div class="inbox-actions">
          <input placeholder="转换标题" data-idea-title="${i.ideaId}" value="${escapeHtml(i.content.slice(0, 24))}">
          <button type="button" class="btn btn-sm btn-primary" data-action="ideaToEvt" data-idea-id="${i.ideaId}">转事项</button>
          <button type="button" class="btn btn-sm" data-action="ideaToDdl" data-idea-id="${i.ideaId}">转 DDL</button>
          <button type="button" class="btn btn-sm" data-action="archiveIdea" data-idea-id="${i.ideaId}">归档</button>
        </div>
      </article>`).join("")
    : '<span class="empty">无匹配灵感</span>';
  renderBoardIdeaInbox(ideas);
  renderSummary(evtCache, ideas, primaryDevState);
}

function syncEvtDetailActions(stat) {
  const canClose = stat === "todo";
  $("completeEvtDetailBtn")?.toggleAttribute("hidden", !canClose);
  $("cancelEvtDetailBtn")?.toggleAttribute("hidden", !canClose);
  $("reopenEvtDetailBtn")?.toggleAttribute("hidden", canClose);
}

function evtTimeFieldName(evt) {
  if (evt.evtType === "life") return "dueAt";
  if (evt.evtType === "ddl") return "ddlAt";
  if (evt.evtType === "course") return "classDate";
  return null;
}

function syncEvtTimeField(evt) {
  const field = $("evtTimeField");
  const form = $("evtDetailForm");
  const input = form?.elements.evtTime;
  const name = evtTimeFieldName(evt);
  if (!field || !input || !name) return;
  form.dataset.timeField = name;
  field.hidden = false;
  input.type = name === "classDate" ? "date" : "datetime-local";
  input.value = toLocalInputValue(evt[name], name === "classDate" ? "date" : "datetime");
  field.firstChild.textContent = name === "classDate" ? "上课日期" : "提醒时间";
}

function populateEvtDetail(evt) {
  const form = $("evtDetailForm");
  if (!form || !evt) return;
  form.dataset.evtId = evt.evtId;
  form.dataset.evtType = evt.evtType || "";
  form.dataset.stat = evt.stat || "todo";
  form.elements.title.value = evt.title || "";
  form.elements.desc.value = evt.desc || "";
  form.elements.stat.value = evt.stat || "todo";
  form.elements.prio.value = evt.prio || "mid";
  syncEvtTimeField(evt);
  syncEvtDetailActions(evt.stat || "todo");
}

function openEvtDetail(evtId) {
  const evt = evtCache.find((e) => e.evtId === evtId);
  if (!evt) return;
  activeEvtId = evtId;
  populateEvtDetail(evt);
  const drawer = $("evtDetailDrawer");
  drawer?.classList.add("open");
  drawer?.setAttribute("aria-hidden", "false");
  markActiveEvtCard(evtId);
  $("evtDetailForm")?.elements.title?.focus();
}

function closeEvtDetail() {
  activeEvtId = null;
  const drawer = $("evtDetailDrawer");
  drawer?.classList.remove("open");
  drawer?.setAttribute("aria-hidden", "true");
  markActiveEvtCard(null);
}

async function saveEvtDetail() {
  const form = $("evtDetailForm");
  const evtId = form?.dataset.evtId;
  if (!evtId) return;
  const resp = await api(`/api/evt/${evtId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: form.elements.title.value.trim(),
      desc: form.elements.desc.value.trim() || null,
      stat: form.elements.stat.value,
      prio: form.elements.prio.value,
      ...(form.dataset.timeField ? {
        [form.dataset.timeField]: form.dataset.timeField === "classDate"
          ? (form.elements.evtTime.value || null)
          : toIsoFromLocal(form.elements.evtTime.value),
      } : {}),
    }),
  });
  if (resp.ok) {
    showFlash("已更新");
    closeEvtDetail();
    await loadEvts();
    await loadActLog();
  }
}

async function completeEvtDetail() {
  const evtId = $("evtDetailForm")?.dataset.evtId;
  if (!evtId) return;
  const resp = await api(`/api/evt/${evtId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stat: "done" }),
  });
  if (resp.ok) {
    showFlash("已完成");
    closeEvtDetail();
    await loadEvts();
    await loadActLog();
  }
}

async function cancelEvtDetail() {
  const evtId = $("evtDetailForm")?.dataset.evtId;
  if (!evtId) return;
  const resp = await api(`/api/evt/${evtId}`, { method: "DELETE" });
  if (resp.ok) {
    showFlash("已取消");
    closeEvtDetail();
    await loadEvts();
    await loadActLog();
  }
}

async function reopenEvtDetail() {
  const evtId = $("evtDetailForm")?.dataset.evtId;
  if (!evtId) return;
  const resp = await api(`/api/evt/${evtId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stat: "todo" }),
  });
  if (resp.ok) {
    showFlash("已恢复为待办");
    closeEvtDetail();
    await loadEvts();
    await loadActLog();
  }
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
  renderIdeaInbox(resp.data || []);
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

function renderDeviceStatus(rows) {
  devCache = rows;
  const filter = $("devStatusFilter")?.value || "";
  const filtered = filter ? rows.filter((r) => r.state === filter) : rows;
  const primary = pickPrimaryDevState(rows);
  primaryDevState = primary;
  renderPrimaryDevState(primary);
  updateWorkPresence(primary);
  const summary = $("deviceSummaryCard");
  if (summary) {
    summary.innerHTML = primary
      ? `<div><span class="dev-badge ${escapeHtml(primary.state)}">${escapeHtml(primary.state)}</span> <strong>${escapeHtml(primary.devId)}</strong></div><div class="log-meta">confidence ${primary.confidence ?? "—"} · ${fmtDtLocal(primary.seenAt)}</div>`
      : '<span class="empty">暂无设备上报</span>';
  }
  $("devStateBody").innerHTML = filtered.length
    ? filtered.slice(0, 24).map((r) => {
        const meta = r.meta && typeof r.meta === "object" ? r.meta : {};
        return `<div class="log-row"><div><span class="dev-badge ${escapeHtml(r.state)}">${escapeHtml(r.state)}</span> ${escapeHtml(r.devId)}<div class="log-row-meta">${escapeHtml(meta.rawStatus || "")} ${escapeHtml(meta.identity || "")}</div></div><div class="log-row-meta">${fmtDtLocal(r.seenAt)}</div></div>`;
      }).join("")
    : '<span class="empty">暂无设备上报</span>';
  renderNotifyRoute(primary);
  renderSummary(evtCache, ideaCache, primary);
}

async function loadDevState() {
  const resp = await api("/api/devState");
  renderDeviceStatus(resp.data || []);
  renderPrimaryDevState(primaryDevState);
}

function filterLogs() {
  renderLogs();
}

function renderLogs() {
  const keyword = ($("logKeyword")?.value || "").trim().toLowerCase();
  const status = ($("logStatusFilter")?.value || "").trim().toLowerCase();
  const match = (text, stat) => {
    const hay = `${text} ${stat || ""}`.toLowerCase();
    if (keyword && !hay.includes(keyword)) return false;
    const norm = (stat || "").toLowerCase();
    if (status === "wait" && !norm.startsWith("pend")) return false;
    if (status && status !== "wait" && !norm.includes(status)) return false;
    return true;
  };
  $("notifyLogList").innerHTML = notifyLogCache.length
    ? notifyLogCache.filter((r) => match(`${r.title} ${r.channel || r.targetKind}`, r.stat)).slice().reverse().slice(0, 60).map((r) => `<div class="log-row"><div class="log-row-title">${escapeHtml(r.title)}</div><div class="log-row-meta">${escapeHtml(r.stat)} · ${escapeHtml(r.channel || r.targetKind || "")} · ${fmtDtLocal(r.scheduledAt)}</div></div>`).join("") || '<span class="empty">无匹配</span>'
    : '<span class="empty">无</span>';
  $("msgLogList").innerHTML = msgLogCache.length
    ? msgLogCache.filter((r) => match(r.rawText || "", r.stat)).slice().reverse().slice(0, 60).map((r) => `<div class="log-row"><div class="log-row-title">${escapeHtml(r.rawText || "—")}</div><div class="log-row-meta">${escapeHtml(r.src)} · ${escapeHtml(r.stat || "—")} · ${fmtDtLocal(r.createdAt)}</div></div>`).join("") || '<span class="empty">无匹配</span>'
    : '<span class="empty">无</span>';
  $("actLogList").innerHTML = actLogCache.length
    ? actLogCache.filter((r) => match(`${r.actType} ${r.targetKind}`, r.stat)).slice().reverse().slice(0, 60).map((r) => `<div class="log-row"><div class="log-row-title">${escapeHtml(r.actType)} → ${escapeHtml(r.targetKind || "")}</div><div class="log-row-meta">${escapeHtml(r.src)} · ${fmtDtLocal(r.createdAt)}${r.undoToken ? ` · <button class="btn btn-sm" data-action="undoAct" data-undo-token="${escapeHtml(r.undoToken)}">undo</button>` : ""}</div></div>`).join("") || '<span class="empty">无匹配</span>'
    : '<span class="empty">无</span>';
}

async function loadNotifyLog() {
  const resp = await api("/api/notifyLog");
  notifyLogCache = resp.data || [];
  renderLogs();
}

async function loadMsgLog() {
  const resp = await api("/api/msgLog");
  msgLogCache = resp.data || [];
  renderLogs();
}

async function loadActLog() {
  const resp = await api("/api/actLog");
  actLogCache = resp.data || [];
  renderLogs();
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
    if (view === "evtAdd") await loadEvts();
    else if (view === "evtBoard" && !isEvtDetailOpen()) await loadEvts();
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
  if (!form) return;
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
      renderCreatePreview();
      await (after || refreshAll)();
    }
  });
}

bindQuickForm("lifeEvtForm", (f) => ({ title: formVal(f, "title"), desc: formVal(f, "desc") || null, dueAt: toIsoFromLocal(formVal(f, "dueAt")), prio: formVal(f, "prio") }), loadEvts);
bindQuickForm("ddlEvtForm", (f) => ({ title: formVal(f, "title"), desc: formVal(f, "desc") || null, ddlAt: toIsoFromLocal(formVal(f, "ddlAt")), hardDdl: f.elements.hardDdl.checked, prio: formVal(f, "prio") }), loadEvts);
bindQuickForm("ideaForm", (f) => ({ content: formVal(f, "content"), srcType: "text" }), loadIdeas);
bindQuickForm("ideaQuickForm", (f) => ({ content: formVal(f, "content"), srcType: "text" }), loadIdeas);
bindQuickForm("courseTplForm", (f) => ({ courseName: formVal(f, "courseName"), teacher: formVal(f, "teacher") || null, room: formVal(f, "room") || null, weekday: Number(formVal(f, "weekday")), startTime: formVal(f, "startTime") || null, endTime: formVal(f, "endTime") || null, startWeek: numOrNull(formVal(f, "startWeek")), endWeek: numOrNull(formVal(f, "endWeek")), weekMode: formVal(f, "weekMode"), semester: formVal(f, "semester") || null }), loadCourses);
bindQuickForm("courseInstForm", (f) => ({ title: formVal(f, "title"), tplId: formVal(f, "tplId"), classDate: formVal(f, "classDate") || null, attendStat: formVal(f, "attendStat") }), loadCourses);

["lifeEvtForm", "ddlEvtForm", "ideaForm"].forEach((id) => {
  $(id)?.addEventListener("input", renderCreatePreview);
});

$("evtDetailForm")?.elements.stat?.addEventListener("change", (ev) => syncEvtDetailActions(ev.target.value));
$("ideaStatusFilter")?.addEventListener("change", (ev) => setIdeaFilter(ev.target.value));
$("devStatusFilter")?.addEventListener("change", () => renderDeviceStatus(devCache));
$("logKeyword")?.addEventListener("input", filterLogs);
$("logStatusFilter")?.addEventListener("change", filterLogs);

document.body.addEventListener("click", async (ev) => {
  const tab = ev.target.closest("[data-view-tab]");
  if (tab) return activeView(tab.dataset.viewTab);
  const createTab = ev.target.closest("[data-create-tab]");
  if (createTab) return setCreateTab(createTab.dataset.createTab);
  const btn = ev.target.closest("[data-action]");
  if (!btn) return;
  if (btn.closest(".board-card-actions")) ev.stopPropagation();
  const a = btn.dataset.action;
  if (a === "refreshAll") await refreshAll();
  else if (a === "refreshEvt") await loadEvts();
  else if (a === "refreshIdea") await loadIdeas();
  else if (a === "refreshCourse") await loadCourses();
  else if (a === "refreshDev") await loadDevState();
  else if (a === "refreshNotify") await loadNotifyLog();
  else if (a === "refreshMsg") await loadMsgLog();
  else if (a === "refreshAct") await loadActLog();
  else if (a === "parseNatural") prefillCreateForm(parseNaturalInput($("naturalInput")?.value));
  else if (a === "applyTemplate") applyTemplate(btn.dataset.template);
  else if (a === "openEvtDetail") openEvtDetail(btn.dataset.evtId);
  else if (a === "closeEvtDetail") closeEvtDetail();
  else if (a === "saveEvtDetail") await saveEvtDetail();
  else if (a === "completeEvtDetail") await completeEvtDetail();
  else if (a === "cancelEvtDetail") await cancelEvtDetail();
  else if (a === "reopenEvtDetail") await reopenEvtDetail();
  else if (a === "completeEvt") await patchEvt(btn.dataset.evtId, { stat: "done" });
  else if (a === "cancelEvt") {
    const resp = await api(`/api/evt/${btn.dataset.evtId}`, { method: "DELETE" });
    if (resp.ok) showFlash("已取消");
    await loadEvts();
    await loadActLog();
  } else if (a === "reopenEvt") await patchEvt(btn.dataset.evtId, { stat: "todo" });
  else if (a === "ideaToEvt") {
    const title = document.querySelector(`[data-idea-title="${btn.dataset.ideaId}"]`)?.value || "灵感事项";
    await api(`/api/idea/${btn.dataset.ideaId}/toEvt`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, dueAt: null }) });
    await Promise.all([loadIdeas(), loadEvts(), loadActLog()]);
  } else if (a === "ideaToDdl") await ideaToDdl(btn.dataset.ideaId);
  else if (a === "archiveIdea") archiveIdea(btn.dataset.ideaId);
  else if (a === "undoAct") {
    await api(`/api/undo/${btn.dataset.undoToken}`, { method: "POST" });
    await refreshAll();
  }
});

document.body.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && isEvtDetailOpen()) {
    ev.preventDefault();
    closeEvtDetail();
    return;
  }
  const card = ev.target.closest('[data-action="openEvtDetail"]');
  if (!card) return;
  if (ev.key === "Enter" || ev.key === " ") {
    ev.preventDefault();
    openEvtDetail(card.dataset.evtId);
  }
});

document.querySelectorAll(".log-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".log-tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll(".log-pane").forEach((p) => p.classList.toggle("active", p.dataset.logPane === tab.dataset.logTab));
  });
});

evtSearchEl?.addEventListener("input", applyEvtSearch);
globalSearchEl?.addEventListener("input", applyEvtSearch);

const initialView = (location.hash || "#evtBoard").slice(1);
activeView(["overview", "evtAdd", "evtBoard", "idea", "course", "dev", "log", "settings"].includes(initialView) ? initialView : "evtBoard");
refreshAll();
setInterval(refreshDevStatePeriodic, DEV_REFRESH_MS);
setInterval(refreshActiveView, VIEW_REFRESH_MS);
