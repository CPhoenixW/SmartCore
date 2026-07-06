const page = document.body.dataset.page;
const $ = (id) => document.getElementById(id);
const state = { events: [], ideas: [], courseTpl: [], courseInst: [], logs: { act: [], notify: [], msg: [] }, selectedEvt: null, selectedTpl: null, logTab: "act", createTab: "life" };
const typeLabels = { life: "生活", ddl: "DDL", course: "课程" };
const prioLabels = { high: "高", mid: "中", low: "低" };

function esc(value) {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;");
}
function toast(text) {
  const el = $("toast");
  if (!el) return;
  el.textContent = text;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2200);
}
function setApiStatus(kind, text) {
  const el = $("apiStatus");
  if (!el) return;
  el.className = `status-pill ${kind || ""}`.trim();
  el.textContent = text;
}
function touchRefresh() {
  const el = $("lastRefresh");
  if (el) el.textContent = "更新于 " + new Date().toLocaleTimeString("zh-CN", { hour12: false });
}
async function apiGet(path) {
  setApiStatus("busy", "API 请求中");
  const resp = await fetch(path);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || data.ok === false) throw new Error(data.detail || data.msg || `HTTP ${resp.status}`);
  setApiStatus("ok", "API 在线");
  return data.data ?? [];
}
async function apiSend(path, options) {
  setApiStatus("busy", "API 请求中");
  const resp = await fetch(path, options);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || data.ok === false) {
    setApiStatus("err", "API 异常");
    throw new Error(data.detail || data.msg || `HTTP ${resp.status}`);
  }
  setApiStatus("ok", "API 在线");
  touchRefresh();
  return data.data;
}
function formVal(form, name) { return form?.elements[name]?.value?.trim() || ""; }
function numOrNull(value) { return value === "" || value == null ? null : Number(value); }
function toIsoFromLocal(value) {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  const pad = (n) => String(n).padStart(2, "0");
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const abs = Math.abs(off);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:00${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}
function toLocalInputValue(value, type = "datetime") {
  if (!value) return "";
  if (type === "date") return String(value).slice(0, 10);
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function eventTime(evt) {
  const raw = evt.evtType === "ddl" ? evt.ddlAt : evt.evtType === "course" ? evt.classDate : evt.dueAt;
  if (!raw) return { date: null, label: "未设置", overdue: false };
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return { date: null, label: raw, overdue: false };
  const today = new Date();
  const tomorrow = new Date();
  tomorrow.setDate(today.getDate() + 1);
  const same = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  const day = same(d, today) ? "今天" : same(d, tomorrow) ? "明天" : `${d.getMonth() + 1}月${d.getDate()}日`;
  const time = d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  const overdue = evt.stat === "todo" && evt.evtType !== "course" && d.getTime() < Date.now();
  return { date: d, label: `${day} ${time}${overdue ? " · 已逾期" : ""}`, overdue };
}
function tagClass(value, kind) {
  if (kind === "type" && value === "ddl") return "purple";
  if (kind === "type" && value === "course") return "green";
  if (kind === "prio" && value === "high") return "red";
  if (kind === "prio" && value === "mid") return "orange";
  return "blue";
}
function rowEmpty(text) { return `<div class="empty">${esc(text)}</div>`; }
function shortText(value, max = 80) {
  const text = String(value || "").trim();
  return text.length > max ? `${text.slice(0, max)}…` : text;
}
function renderTaskRow(evt, withActions = false) {
  const t = eventTime(evt);
  return `<article class="task-row" data-evt-id="${esc(evt.evtId)}">
    <div>
      <div class="task-title">${esc(evt.title)}</div>
      <div class="tags">
        <span class="tag ${tagClass(evt.evtType, "type")}">${esc(typeLabels[evt.evtType] || evt.evtType)}</span>
        <span class="tag ${tagClass(evt.prio, "prio")}">${esc(prioLabels[evt.prio] || evt.prio || "中")}</span>
        <span class="tag ${t.overdue ? "red" : "blue"}">${esc(t.label)}</span>
      </div>
      ${evt.desc ? `<p class="task-desc">${esc(shortText(evt.desc, 100))}</p>` : ""}
    </div>
    ${withActions ? `<div class="task-actions"><button class="btn" data-action="selectEvt" data-id="${esc(evt.evtId)}">编辑</button></div>` : ""}
  </article>`;
}
async function loadEvents() { state.events = await apiGet("/api/evt"); return state.events; }
async function loadIdeas() { state.ideas = await apiGet("/api/idea"); return state.ideas; }
async function loadCourses() { const [tpl, inst] = await Promise.all([apiGet("/api/courseTpl"), apiGet("/api/courseInst")]); state.courseTpl = tpl; state.courseInst = inst; }

function renderOverview() {
  const todos = state.events.filter((e) => e.stat === "todo");
  const deadline = todos.filter((e) => { const t = eventTime(e); if (!t.date || e.evtType === "course") return false; const diff = t.date.getTime() - Date.now(); return diff >= 0 && diff <= 48 * 3600_000; });
  const openIdeas = state.ideas.filter((i) => !i.handled);
  $("ovTodo").textContent = todos.length;
  $("ovDeadline").textContent = deadline.length;
  $("ovIdeas").textContent = openIdeas.length;
  const dev = state.devState;
  $("ovDevice").textContent = dev?.state || "—";
  $("overviewTasks").innerHTML = todos.slice(0, 6).map((e) => renderTaskRow(e)).join("") || rowEmpty("暂无待办事项");
  $("overviewTimeline").innerHTML = deadline.slice(0, 6).map((e) => renderTaskRow(e)).join("") || rowEmpty("48 小时内无截止事项");
  $("overviewIdeas").innerHTML = openIdeas.slice(-5).reverse().map((i) => `<div class="row-card"><div class="row-title">${esc(shortText(i.content, 80))}</div><div class="row-meta">${esc(i.createdAt || "")}</div></div>`).join("") || rowEmpty("暂无待整理灵感");
  const route = dev?.state === "working" ? ["在工位", "副屏提醒"] : ["离开", "飞书提醒"];
  $("overviewRoute").innerHTML = `<div class="route-row"><strong>${route[0]}</strong><span>→</span><strong>${route[1]}</strong></div>`;
}
async function initOverview() {
  try {
    const [events, ideas, devRows] = await Promise.all([apiGet("/api/evt"), apiGet("/api/idea"), apiGet("/api/devState")]);
    state.events = events; state.ideas = ideas; state.devState = devRows.find((r) => r.devId === "pi") || devRows[0] || null;
    renderOverview(); touchRefresh();
  } catch (err) { toast(err.message); setApiStatus("err", "API 异常"); renderOverview(); }
}

function setCreateTab(tab) {
  state.createTab = tab;
  document.querySelectorAll("[data-create-tab]").forEach((btn) => btn.classList.toggle("active", btn.dataset.createTab === tab));
  $("lifeForm")?.classList.toggle("active", tab === "life");
  $("ddlForm")?.classList.toggle("active", tab === "ddl");
  renderCreatePreview();
}
function createForm() { return state.createTab === "ddl" ? $("ddlForm") : $("lifeForm"); }
function createPayload() {
  const form = createForm();
  if (state.createTab === "ddl") return { title: formVal(form, "title"), desc: formVal(form, "desc") || null, ddlAt: toIsoFromLocal(formVal(form, "ddlAt")), hardDdl: form.elements.hardDdl.checked, prio: formVal(form, "prio") || "mid" };
  return { title: formVal(form, "title"), desc: formVal(form, "desc") || null, dueAt: toIsoFromLocal(formVal(form, "dueAt")), prio: formVal(form, "prio") || "mid" };
}
function renderCreatePreview() {
  const body = $("createPreview"); if (!body) return;
  const p = createPayload();
  const title = p.title || "等待填写标题";
  const time = state.createTab === "ddl" ? (formVal(createForm(), "ddlAt") || "未设置") : (formVal(createForm(), "dueAt") || "未设置");
  body.innerHTML = `<div class="preview-card"><div class="preview-title">${esc(title)}</div><div class="tags"><span class="tag ${state.createTab === "ddl" ? "purple" : "blue"}">${state.createTab === "ddl" ? "DDL" : "普通事项"}</span><span class="tag ${tagClass(p.prio, "prio")}">${esc(prioLabels[p.prio] || p.prio)}</span><span class="tag blue">${esc(time)}</span></div>${p.desc ? `<p class="preview-desc">${esc(p.desc)}</p>` : ""}</div>`;
}
function parseChineseNumber(raw) {
  const map = { 零: 0, 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10 };
  if (/^\d+$/.test(raw)) return Number(raw);
  if (raw === "十") return 10;
  if (raw.startsWith("十")) return 10 + (map[raw.slice(1)] || 0);
  if (raw.endsWith("十")) return (map[raw[0]] || 1) * 10;
  if (raw.includes("十")) { const [a, b] = raw.split("十"); return (map[a] || 1) * 10 + (map[b] || 0); }
  return map[raw] ?? null;
}
function localParse(text) {
  const isDdl = /ddl|deadline|截止|交|提交|作业|考试|复习/iu.test(text);
  const d = new Date();
  if (/后天/u.test(text)) d.setDate(d.getDate() + 2); else if (/明天/u.test(text)) d.setDate(d.getDate() + 1);
  const m = text.match(/(上午|中午|下午|晚上|今晚|早上)?\s*([零一二两三四五六七八九十\d]{1,3})\s*(点|时)(半|[零一二三四五六七八九十\d]{1,2}分?)?/u);
  if (m) { let h = parseChineseNumber(m[2]) ?? 20; let min = m[4] === "半" ? 30 : m[4] ? parseChineseNumber(m[4].replace("分", "")) || 0 : 0; const part = m[1] || ""; if ((part.includes("下午") || part.includes("晚上") || part.includes("今晚")) && h < 12) h += 12; d.setHours(h, min, 0, 0); } else d.setHours(isDdl ? 23 : 20, 0, 0, 0);
  return { tab: isDdl ? "ddl" : "life", title: text.replace(/^(帮我|提醒我|创建|添加|新建|安排)\s*/u, "").slice(0, 90), desc: text, prio: /高优先级|优先级高|紧急|重要/iu.test(text) ? "high" : /低优先级|优先级低/iu.test(text) ? "low" : "mid", at: toLocalInputValue(d), hardDdl: /硬性|必须|一定|截止/iu.test(text) };
}
function applyParsed(parsed) {
  setCreateTab(parsed.tab || "life");
  const form = createForm();
  form.elements.title.value = parsed.title || "";
  form.elements.desc.value = parsed.desc || "";
  form.elements.prio.value = parsed.prio || "mid";
  if (state.createTab === "ddl") { form.elements.ddlAt.value = parsed.at || parsed.ddlAt || ""; form.elements.hardDdl.checked = Boolean(parsed.hardDdl); }
  else form.elements.dueAt.value = parsed.at || parsed.dueAt || "";
  renderCreatePreview();
}
async function parseNatural() {
  const text = $("naturalText")?.value.trim(); if (!text) return toast("请先输入内容");
  let parsed = null;
  try { const resp = await apiSend("/api/llm/parse", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, scene: "create_event" }) }); parsed = resp?.parsed; } catch { parsed = null; }
  applyParsed(parsed || localParse(text));
  toast("已预填，请确认后创建");
}
async function submitCreate(ev) {
  ev.preventDefault();
  const form = ev.currentTarget;
  const body = createPayload();
  if (!body.title) return toast("请填写标题");
  const endpoint = form.dataset.endpoint;
  try { await apiSend(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); form.reset(); renderCreatePreview(); toast("创建成功"); }
  catch (err) { toast(err.message); }
}
function applyTemplate(name) {
  const d = new Date(); d.setDate(d.getDate() + 1); d.setHours(23, 59, 0, 0);
  if (name === "homework" || name === "exam") { setCreateTab("ddl"); const f = $("ddlForm"); f.elements.title.value = name === "homework" ? "作业 DDL" : "考试复习"; f.elements.desc.value = name === "homework" ? "课程作业截止" : "复习重点章节并完成例题"; f.elements.ddlAt.value = toLocalInputValue(d); f.elements.prio.value = "high"; f.elements.hardDdl.checked = name === "homework"; }
  else { setCreateTab("life"); const f = $("lifeForm"); f.elements.title.value = name === "project" ? "项目跟进" : "生活提醒"; f.elements.desc.value = name === "project" ? "检查阶段任务进展" : ""; f.elements.dueAt.value = toLocalInputValue(d); f.elements.prio.value = "mid"; }
  renderCreatePreview();
}
function initAdd() {
  document.querySelectorAll("[data-create-tab]").forEach((b) => b.addEventListener("click", () => setCreateTab(b.dataset.createTab)));
  document.querySelectorAll("#lifeForm,#ddlForm").forEach((f) => { f.addEventListener("input", renderCreatePreview); f.addEventListener("change", renderCreatePreview); f.addEventListener("submit", submitCreate); });
  document.querySelectorAll(".template").forEach((b) => b.addEventListener("click", () => applyTemplate(b.dataset.template)));
  $("parseNaturalBtn")?.addEventListener("click", parseNatural); renderCreatePreview();
}

function renderUpdateList() {
  const q = $("globalSearch")?.value.trim().toLowerCase() || "";
  const stat = $("evtStatusFilter")?.value || "todo";
  const rows = state.events.filter((e) => (stat === "all" || e.stat === stat) && (!q || `${e.title} ${e.desc || ""}`.toLowerCase().includes(q)));
  $("evtList").innerHTML = rows.length ? rows.map((e) => renderTaskRow(e, true)).join("") : rowEmpty("暂无匹配事件");
}
function fillEvtForm(evt) {
  state.selectedEvt = evt;
  const f = $("evtEditForm");
  f.elements.evtId.value = evt.evtId; f.elements.title.value = evt.title || ""; f.elements.desc.value = evt.desc || ""; f.elements.stat.value = evt.stat || "todo"; f.elements.prio.value = evt.prio || "mid";
  const timeName = evt.evtType === "ddl" ? "ddlAt" : evt.evtType === "course" ? "classDate" : "dueAt";
  f.dataset.timeField = timeName;
  f.elements.evtTime.type = timeName === "classDate" ? "date" : "datetime-local";
  f.elements.evtTime.value = toLocalInputValue(evt[timeName], timeName === "classDate" ? "date" : "datetime");
  $("hardDdlField")?.classList.toggle("hidden", evt.evtType !== "ddl");
  f.elements.hardDdl.checked = Boolean(evt.hardDdl);
}
async function saveEvt(ev) {
  ev.preventDefault();
  const f = ev.currentTarget; const evtId = formVal(f, "evtId"); if (!evtId) return toast("请选择事件");
  const body = { title: formVal(f, "title"), desc: formVal(f, "desc") || null, stat: formVal(f, "stat"), prio: formVal(f, "prio") };
  const field = f.dataset.timeField;
  if (field) body[field] = field === "classDate" ? formVal(f, "evtTime") || null : toIsoFromLocal(formVal(f, "evtTime"));
  if (state.selectedEvt?.evtType === "ddl") body.hardDdl = f.elements.hardDdl.checked;
  try { await apiSend(`/api/evt/${evtId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); toast("已保存"); await initUpdate(false); } catch (err) { toast(err.message); }
}
async function initUpdate(showLoading = true) {
  try { if (showLoading) setApiStatus("busy", "API 请求中"); await loadEvents(); renderUpdateList(); touchRefresh(); } catch (err) { toast(err.message); setApiStatus("err", "API 异常"); }
}

function renderIdeas() {
  const filter = $("ideaFilter")?.value || "open";
  const rows = state.ideas.filter((i) => filter === "all" || (filter === "open" ? !i.handled : i.handled));
  $("ideaList").innerHTML = rows.length ? rows.slice().reverse().map((i) => `<div class="row-card"><div class="row-title">${esc(i.content)}</div><div class="row-meta">${i.handled ? "handled" : "open"} · ${esc(i.createdAt || "")}</div><div class="row-actions"><button class="btn" data-action="selectIdea" data-id="${esc(i.ideaId)}">转事项</button><button class="btn" data-action="toggleIdea" data-id="${esc(i.ideaId)}" data-handled="${i.handled ? "0" : "1"}">${i.handled ? "标为 open" : "标为 handled"}</button><button class="btn btn-danger" data-action="deleteIdea" data-id="${esc(i.ideaId)}">删除</button></div></div>`).join("") : rowEmpty("暂无灵感");
}
async function initInspire() { try { await loadIdeas(); renderIdeas(); touchRefresh(); } catch (err) { toast(err.message); setApiStatus("err", "API 异常"); } }
async function saveIdea() { const content = $("ideaContent").value.trim(); if (!content) return toast("请填写灵感"); try { await apiSend("/api/idea", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content, srcType: "text" }) }); $("ideaContent").value = ""; await initInspire(); toast("已保存"); } catch (err) { toast(err.message); } }
async function convertIdea(ev) { ev.preventDefault(); const f = ev.currentTarget; const ideaId = formVal(f, "ideaId"); if (!ideaId) return toast("请选择灵感"); try { await apiSend(`/api/idea/${ideaId}/toEvt`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: formVal(f, "title"), dueAt: toIsoFromLocal(formVal(f, "dueAt")) }) }); f.reset(); await initInspire(); toast("已转为事项"); } catch (err) { toast(err.message); } }

function renderCourse() {
  $("courseTplList").innerHTML = state.courseTpl.length ? state.courseTpl.map((c) => `<div class="row-card"><div class="row-title">${esc(c.courseName)}</div><div class="row-meta">周${esc(c.weekday)} · ${esc(c.startTime || "—")} - ${esc(c.endTime || "—")} · ${esc(c.room || "")}</div><div class="row-actions"><button class="btn" data-action="editTpl" data-id="${esc(c.tplId)}">编辑</button></div></div>`).join("") : rowEmpty("暂无课程模板");
  $("courseInstList").innerHTML = state.courseInst.length ? state.courseInst.map((c) => renderTaskRow(c)).join("") : rowEmpty("暂无课程实例");
}
function fillCourseTpl(tpl = null) { const f = $("courseTplForm"); f.reset(); f.elements.tplId.value = tpl?.tplId || ""; for (const key of ["courseName", "teacher", "room", "weekday", "startTime", "endTime", "startWeek", "endWeek", "weekMode", "semester"]) if (tpl?.[key] != null) f.elements[key].value = tpl[key]; }
async function saveCourseTpl(ev) { ev.preventDefault(); const f = ev.currentTarget; const body = { courseName: formVal(f, "courseName"), teacher: formVal(f, "teacher") || null, room: formVal(f, "room") || null, weekday: Number(formVal(f, "weekday")), startTime: formVal(f, "startTime") || null, endTime: formVal(f, "endTime") || null, startWeek: numOrNull(formVal(f, "startWeek")), endWeek: numOrNull(formVal(f, "endWeek")), weekMode: formVal(f, "weekMode") || "all", semester: formVal(f, "semester") || null }; const id = formVal(f, "tplId"); try { await apiSend(id ? `/api/courseTpl/${id}` : "/api/courseTpl", { method: id ? "PATCH" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); await initCourse(false); toast("已保存课程"); } catch (err) { toast(err.message); } }
async function initCourse(showLoading = true) { try { if (showLoading) setApiStatus("busy", "API 请求中"); await loadCourses(); renderCourse(); touchRefresh(); } catch (err) { toast(err.message); setApiStatus("err", "API 异常"); } }

function renderLogs() {
  const q = $("logKeyword")?.value.trim().toLowerCase() || "";
  const rows = (state.logs[state.logTab] || []).slice().reverse().filter((r) => !q || JSON.stringify(r).toLowerCase().includes(q));
  $("logList").innerHTML = rows.length ? rows.slice(0, 80).map((r) => `<div class="log-row"><div class="row-title">${esc(r.actType || r.title || r.rawText || r.msgId || r.notifyId || r.actId || "日志")}</div><div class="row-meta">${esc(r.createdAt || r.scheduledAt || "")} · ${esc(r.stat || r.src || "")}</div><pre class="log-json">${esc(JSON.stringify(r, null, 2))}</pre></div>`).join("") : rowEmpty("暂无日志");
}
async function initLog() { try { const [act, notify, msg] = await Promise.all([apiGet("/api/actLog"), apiGet("/api/notifyLog"), apiGet("/api/msgLog")]); state.logs = { act, notify, msg }; renderLogs(); touchRefresh(); } catch (err) { toast(err.message); setApiStatus("err", "API 异常"); } }

function bindCommon() {
  $("refreshPageBtn")?.addEventListener("click", () => initPage());
  $("globalSearch")?.addEventListener("input", () => { if (page === "update") renderUpdateList(); });
  document.body.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-action]"); if (!btn) return;
    if (btn.dataset.action === "selectEvt") { const evt = state.events.find((e) => e.evtId === btn.dataset.id); if (evt) fillEvtForm(evt); }
    if (btn.dataset.action === "selectIdea") { const idea = state.ideas.find((i) => i.ideaId === btn.dataset.id); const f = $("ideaToEvtForm"); if (idea && f) { f.elements.ideaId.value = idea.ideaId; f.elements.ideaTitle.value = shortText(idea.content, 40); f.elements.title.value = shortText(idea.content, 36); } }
    if (btn.dataset.action === "toggleIdea") { try { await apiSend(`/api/idea/${btn.dataset.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ handled: btn.dataset.handled === "1" }) }); await initInspire(); } catch (err) { toast(err.message); } }
    if (btn.dataset.action === "deleteIdea") { try { await apiSend(`/api/idea/${btn.dataset.id}`, { method: "DELETE" }); await initInspire(); } catch (err) { toast(err.message); } }
    if (btn.dataset.action === "editTpl") { const tpl = state.courseTpl.find((c) => c.tplId === btn.dataset.id); fillCourseTpl(tpl); }
  });
}
function bindPage() {
  if (page === "add") initAdd();
  if (page === "update") { $("evtEditForm")?.addEventListener("submit", saveEvt); $("evtStatusFilter")?.addEventListener("change", renderUpdateList); $("markDoneBtn")?.addEventListener("click", async () => { const id = formVal($("evtEditForm"), "evtId"); if (id) { await apiSend(`/api/evt/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stat: "done" }) }); await initUpdate(false); toast("已完成"); }}); $("cancelEvtBtn")?.addEventListener("click", async () => { const id = formVal($("evtEditForm"), "evtId"); if (id) { await apiSend(`/api/evt/${id}`, { method: "DELETE" }); await initUpdate(false); toast("已取消"); }}); }
  if (page === "inspire") { $("saveIdeaBtn")?.addEventListener("click", saveIdea); $("ideaFilter")?.addEventListener("change", renderIdeas); $("ideaToEvtForm")?.addEventListener("submit", convertIdea); }
  if (page === "course") { $("courseTplForm")?.addEventListener("submit", saveCourseTpl); $("newCourseBtn")?.addEventListener("click", () => fillCourseTpl(null)); $("deleteCourseTplBtn")?.addEventListener("click", async () => { const id = formVal($("courseTplForm"), "tplId"); if (!id) return toast("请选择课程模板"); try { await apiSend(`/api/courseTpl/${id}`, { method: "DELETE" }); fillCourseTpl(null); await initCourse(false); toast("已删除"); } catch (err) { toast(err.message); } }); }
  if (page === "log") { document.querySelectorAll("[data-log-tab]").forEach((b) => b.addEventListener("click", () => { state.logTab = b.dataset.logTab; document.querySelectorAll("[data-log-tab]").forEach((x) => x.classList.toggle("active", x === b)); renderLogs(); })); $("logKeyword")?.addEventListener("input", renderLogs); }
}
async function initPage() {
  if (page === "overview") return initOverview();
  if (page === "update") return initUpdate();
  if (page === "inspire") return initInspire();
  if (page === "course") return initCourse();
  if (page === "log") return initLog();
}

bindCommon();
bindPage();
initPage();
