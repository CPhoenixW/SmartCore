import { ensureDeviceNav, formatDateTime, getUiLanguage, t } from "./work_shared.js";

const $ = (id) => document.getElementById(id);
const state = { events: [], selectedId: null, date: "" };
const typeLabels = { plan: ["计划", "Plan"], ddl: ["DDL", "DDL"] };
const prioLabels = { high: ["高", "High"], mid: ["中", "Medium"], low: ["低", "Low"] };

function ui(zh, en) { return getUiLanguage() === "en" ? en : zh; }
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
function setApi(kind, text) {
  const el = $("apiStatus");
  if (!el) return;
  el.className = `status-pill ${kind || ""}`.trim();
  el.textContent = text;
}
async function api(path, options = undefined) {
  setApi("busy", t("API 请求中"));
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.ok === false) {
    setApi("err", t("API 异常"));
    throw new Error(body.detail || body.msg || `HTTP ${response.status}`);
  }
  setApi("ok", t("API 在线"));
  if ($("lastRefresh")) $("lastRefresh").textContent = ui(`更新于 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`, `Updated at ${new Date().toLocaleTimeString("en-US", { hour12: false })}`);
  return body.data;
}
function localDateValue(date = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
function shiftDate(value, days) {
  const date = new Date(`${value}T12:00:00`);
  date.setDate(date.getDate() + days);
  return localDateValue(date);
}
function toLocalInput(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (part) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
function toIso(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const pad = (part) => String(part).padStart(2, "0");
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  const absolute = Math.abs(offset);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:00${sign}${pad(Math.floor(absolute / 60))}:${pad(absolute % 60)}`;
}
function val(form, name) { return form?.elements[name]?.value?.trim() || ""; }
function eventInstant(event) { return new Date(event.stTime || event.endTime || 0); }
function eventLabel(event) {
  const date = eventInstant(event);
  if (Number.isNaN(date.getTime())) return ui("未设置", "Not set");
  const start = date.toLocaleTimeString(getUiLanguage() === "en" ? "en-US" : "zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  if (event.evtType === "ddl") return ui(`截止 ${start}`, `Due ${start}`);
  const end = new Date(date.getTime() + Number(event.durationMin || 0) * 60000);
  return `${start}–${end.toLocaleTimeString(getUiLanguage() === "en" ? "en-US" : "zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })}`;
}
function tagClass(value, kind) {
  if (kind === "type" && value === "ddl") return "purple";
  if (kind === "prio" && value === "high") return "red";
  if (kind === "prio" && value === "mid") return "orange";
  return "blue";
}
function render() {
  const query = $("globalSearch")?.value.trim().toLowerCase() || "";
  const status = $("evtStatusFilter")?.value || "todo";
  const rows = state.events
    .filter((event) => (status === "all" || event.stat === status))
    .filter((event) => !query || `${event.title} ${event.desc || ""}`.toLowerCase().includes(query))
    .sort((a, b) => eventInstant(a) - eventInstant(b));
  $("evtList").innerHTML = rows.length ? rows.map((event) => {
    const typePair = typeLabels[event.evtType] || [event.evtType, event.evtType];
    const prioPair = prioLabels[event.prio] || [event.prio, event.prio];
    return `<article class="task-row clickable ${state.selectedId === event.evtId ? "selected" : ""}" data-event-id="${esc(event.evtId)}" tabindex="0" role="button"><div><div class="task-title">${esc(event.title)}</div><div class="tags"><span class="tag ${tagClass(event.evtType, "type")}">${esc(typePair[getUiLanguage() === "en" ? 1 : 0])}</span><span class="tag ${tagClass(event.prio, "prio")}">${esc(prioPair[getUiLanguage() === "en" ? 1 : 0])}</span><span class="tag blue">${esc(eventLabel(event))}</span>${event.generatedBy === "course" ? `<span class="tag green">${esc(ui("课程生成", "Course"))}</span>` : ""}</div>${event.desc ? `<p class="task-desc">${esc(event.desc)}</p>` : ""}</div></article>`;
  }).join("") : `<div class="empty">${esc(ui("当天暂无匹配事件", "No matching events for this day"))}</div>`;
  const date = new Date(`${state.date}T12:00:00`);
  $("selectedDateTitle").textContent = date.toLocaleDateString(getUiLanguage() === "en" ? "en-US" : "zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long" });
  $("selectedDateCount").textContent = ui(`${rows.length} 个事项`, `${rows.length} events`);
}
function selectEvent(event) {
  state.selectedId = event.evtId;
  const form = $("evtEditForm");
  form.elements.evtId.value = event.evtId;
  form.elements.evtType.value = event.evtType;
  form.elements.title.value = event.title || "";
  form.elements.desc.value = event.desc || "";
  form.elements.stat.value = event.stat || "todo";
  form.elements.prio.value = event.prio || "mid";
  form.dataset.timeField = event.evtType === "ddl" ? "endTime" : "stTime";
  form.elements.evtTime.value = toLocalInput(event[form.dataset.timeField]);
  $("durationField").classList.toggle("hidden", event.evtType !== "plan");
  form.elements.durationMin.value = event.durationMin || 30;
  $("hardDdlField").classList.toggle("hidden", event.evtType !== "ddl");
  form.elements.hardDdl.checked = Boolean(event.hardDdl);
  render();
}
async function load() {
  state.events = await api(`/api/evt?date=${encodeURIComponent(state.date)}&includeCourseTemplates=false`);
  const queryId = new URLSearchParams(location.search).get("evtId");
  const current = state.events.find((event) => event.evtId === (state.selectedId || queryId));
  if (current) selectEvent(current); else render();
}
async function save(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const id = val(form, "evtId");
  if (!id) return toast(ui("请选择事件", "Select an event"));
  const payload = { title: val(form, "title"), desc: val(form, "desc") || null, stat: val(form, "stat"), prio: val(form, "prio") };
  payload[form.dataset.timeField] = toIso(val(form, "evtTime"));
  if (val(form, "evtType") === "plan") payload.durationMin = Number(val(form, "durationMin") || 30);
  if (val(form, "evtType") === "ddl") payload.hardDdl = form.elements.hardDdl.checked;
  try {
    await api(`/api/evt/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    toast(ui("已保存，关联提醒已同步", "Saved; linked reminders synchronized"));
    await load();
  } catch (error) { toast(error.message); }
}
async function setStatus(status) {
  const id = val($("evtEditForm"), "evtId");
  if (!id) return toast(ui("请选择事件", "Select an event"));
  try {
    await api(`/api/evt/${id}`, status === "cancelled" ? { method: "DELETE" } : { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stat: status }) });
    state.selectedId = null;
    await load();
  } catch (error) { toast(error.message); }
}
function setDate(value) {
  state.date = value;
  $("evtDateFilter").value = value;
  history.replaceState(null, "", `/work/update?date=${encodeURIComponent(value)}`);
  state.selectedId = null;
  load().catch((error) => toast(error.message));
}
function bind() {
  $("evtEditForm")?.addEventListener("submit", save);
  $("markDoneBtn")?.addEventListener("click", () => setStatus("done"));
  $("cancelEvtBtn")?.addEventListener("click", () => setStatus("cancelled"));
  $("evtStatusFilter")?.addEventListener("change", render);
  $("globalSearch")?.addEventListener("input", render);
  $("evtDateFilter")?.addEventListener("change", (event) => setDate(event.target.value));
  $("prevDayBtn")?.addEventListener("click", () => setDate(shiftDate(state.date, -1)));
  $("nextDayBtn")?.addEventListener("click", () => setDate(shiftDate(state.date, 1)));
  $("todayBtn")?.addEventListener("click", () => setDate(localDateValue()));
  document.body.addEventListener("click", (event) => {
    const row = event.target.closest("[data-event-id]");
    const item = state.events.find((entry) => entry.evtId === row?.dataset.eventId);
    if (item) selectEvent(item);
  });
  document.body.addEventListener("keydown", (event) => {
    const row = event.target.closest?.("[data-event-id]");
    if (row && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); row.click(); }
  });
  window.addEventListener("smartcore:languagechange", render);
}

ensureDeviceNav(false);
bind();
state.date = new URLSearchParams(location.search).get("date") || localDateValue();
$("evtDateFilter").value = state.date;
load().catch((error) => toast(error.message));
