import { ensureDeviceNav, getUiLanguage, t } from "./work_shared.js";

const $ = (id) => document.getElementById(id);
const state = { events: [], selectedId: null, date: "", searchTimer: null };
const typeLabels = { plan: ["计划", "Plan"], ddl: ["DDL", "DDL"] };
const prioLabels = { high: ["高", "High"], mid: ["中", "Medium"], low: ["低", "Low"] };
const weekdayLabels = {
  1: ["星期一", "monday"], 2: ["星期二", "tuesday"], 3: ["星期三", "wednesday"],
  4: ["星期四", "thursday"], 5: ["星期五", "friday"], 6: ["星期六", "saturday"],
  7: ["星期日", "sunday"],
};

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
function normalizeQuery(value) {
  let text = String(value || "").trim().toLowerCase().replace(/\//g, "-");
  text = text.replace(/(\d{1,2})点半/g, (_, hour) => `${String(Number(hour)).padStart(2, "0")}:30`);
  text = text.replace(/(\d{1,2})点(?:(\d{1,2})分?)?/g, (_, hour, minute) => `${String(Number(hour)).padStart(2, "0")}:${String(Number(minute || 0)).padStart(2, "0")}`);
  return text;
}
function extractDateQuery(value) {
  const text = String(value || "");
  const match = text.match(/(20\d{2})[年\-/](\d{1,2})[月\-/](\d{1,2})日?/);
  if (!match) return null;
  const candidate = `${match[1]}-${String(Number(match[2])).padStart(2, "0")}-${String(Number(match[3])).padStart(2, "0")}`;
  const parsed = new Date(`${candidate}T12:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : candidate;
}
function eventSearchText(event) {
  const instant = eventInstant(event);
  const parts = [event.title, event.desc, event.courseName, event.location, event.teacher, event.evtType, event.prio, event.stat, event.stTime, event.endTime, event.occurrenceDate];
  if (!Number.isNaN(instant.getTime())) {
    const pad = (part) => String(part).padStart(2, "0");
    const isoDate = localDateValue(instant);
    const start = `${pad(instant.getHours())}:${pad(instant.getMinutes())}`;
    const end = new Date(instant.getTime() + Number(event.durationMin || 0) * 60000);
    const endTime = `${pad(end.getHours())}:${pad(end.getMinutes())}`;
    const weekday = instant.getDay() === 0 ? 7 : instant.getDay();
    parts.push(isoDate, isoDate.replace(/-/g, "/"), `${instant.getMonth() + 1}月${instant.getDate()}日`, start, endTime, `${instant.getHours()}点`, weekdayLabels[weekday]?.[0], weekdayLabels[weekday]?.[1]);
  }
  return parts.filter(Boolean).join(" ").toLowerCase();
}
function tagClass(value, kind) {
  if (kind === "type" && value === "ddl") return "purple";
  if (kind === "prio" && value === "high") return "red";
  if (kind === "prio" && value === "mid") return "orange";
  return "blue";
}
function render() {
  const query = normalizeQuery($("globalSearch")?.value);
  const status = $("evtStatusFilter")?.value || "todo";
  const rows = state.events
    .filter((event) => status === "all" || event.stat === status)
    .filter((event) => !query || eventSearchText(event).includes(query))
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
  const query = normalizeQuery($("globalSearch")?.value);
  const textParam = query ? `&text=${encodeURIComponent(query)}` : "";
  state.events = await api(`/api/evt?date=${encodeURIComponent(state.date)}&includeCourseTemplates=false${textParam}`);
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
function handleSearchInput() {
  clearTimeout(state.searchTimer);
  state.searchTimer = setTimeout(() => {
    const dateQuery = extractDateQuery($("globalSearch")?.value);
    if (dateQuery && dateQuery !== state.date) {
      setDate(dateQuery);
      return;
    }
    load().catch((error) => toast(error.message));
  }, 220);
}
function bind() {
  $("evtEditForm")?.addEventListener("submit", save);
  $("markDoneBtn")?.addEventListener("click", () => setStatus("done"));
  $("cancelEvtBtn")?.addEventListener("click", () => setStatus("cancelled"));
  $("evtStatusFilter")?.addEventListener("change", render);
  $("globalSearch")?.addEventListener("input", handleSearchInput);
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
