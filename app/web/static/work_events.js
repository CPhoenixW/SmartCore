import {
  deviceStateView,
  ensureDeviceNav,
  formatDateTime,
  getUiLanguage,
} from "./work_shared.js";

const $ = (id) => document.getElementById(id);
const state = { events: [], ideas: [], deviceStates: [] };

function ui(zh, en) {
  return getUiLanguage() === "en" ? en : zh;
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;");
}

function toast(text) {
  const element = $("toast");
  if (!element) return;
  element.textContent = text;
  element.classList.add("show");
  setTimeout(() => element.classList.remove("show"), 2200);
}

function setApi(kind, text) {
  const element = $("apiStatus");
  if (!element) return;
  element.className = `status-pill ${kind || ""}`.trim();
  element.textContent = text;
}

function markRefresh() {
  const element = $("lastRefresh");
  if (!element) return;
  element.textContent = ui(
    `更新于 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`,
    `Updated at ${new Date().toLocaleTimeString("en-US", { hour12: false })}`,
  );
}

async function getData(url) {
  const response = await fetch(url, { cache: "no-store" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.ok === false) {
    throw new Error(body.detail || body.msg || `HTTP ${response.status}`);
  }
  return body.data || [];
}

function eventStartDate(event) {
  if (event.evtType === "ddl") return event.endTime ? new Date(event.endTime) : null;
  if (event.evtType === "remind") return event.triggerTime ? new Date(event.triggerTime) : null;
  return event.stTime ? new Date(event.stTime) : null;
}

function eventEndDate(event) {
  const start = eventStartDate(event);
  if (!start || Number.isNaN(start.getTime())) return null;
  if (event.evtType === "plan") {
    return new Date(start.getTime() + Math.max(1, Number(event.durationMin || 1)) * 60000);
  }
  return start;
}

function sameDay(left, right) {
  return left.getFullYear() === right.getFullYear()
    && left.getMonth() === right.getMonth()
    && left.getDate() === right.getDate();
}

function localDateValue(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function eventView(event) {
  const start = eventStartDate(event);
  if (!start || Number.isNaN(start.getTime())) {
    return { start: null, end: null, label: ui("未设置", "Not set"), today: false, overdue: false };
  }
  const end = eventEndDate(event);
  const now = new Date();
  const tomorrow = new Date(now);
  tomorrow.setDate(now.getDate() + 1);
  const day = sameDay(start, now)
    ? ui("今天", "Today")
    : sameDay(start, tomorrow)
      ? ui("明天", "Tomorrow")
      : start.toLocaleDateString(getUiLanguage() === "en" ? "en-US" : "zh-CN", {
          month: "short",
          day: "numeric",
        });
  const startTime = start.toLocaleTimeString(getUiLanguage() === "en" ? "en-US" : "zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const endTime = end?.toLocaleTimeString(getUiLanguage() === "en" ? "en-US" : "zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  let timeLabel = startTime;
  if (event.evtType === "ddl") timeLabel = ui(`截止 ${startTime}`, `Due ${startTime}`);
  if (event.evtType === "remind") timeLabel = ui(`提醒 ${startTime}`, `Reminder ${startTime}`);
  if (event.evtType === "plan" && endTime) timeLabel = `${startTime}–${endTime}`;
  const overdue = event.stat === "todo" && end && end.getTime() < now.getTime();
  return {
    start,
    end,
    today: sameDay(start, now) || Boolean(end && sameDay(end, now)),
    overdue,
    label: `${day} ${timeLabel}${overdue ? ui(" · 已逾期", " · Overdue") : ""}`,
  };
}

function statusRank(status) {
  if (status === "todo") return 0;
  if (status === "done") return 1;
  return 2;
}

function sortEvents(events) {
  return events.slice().sort((left, right) => {
    const leftView = eventView(left);
    const rightView = eventView(right);
    if (leftView.overdue !== rightView.overdue) return leftView.overdue ? -1 : 1;
    if (leftView.start && rightView.start && leftView.start.getTime() !== rightView.start.getTime()) {
      return leftView.start.getTime() - rightView.start.getTime();
    }
    return statusRank(left.stat) - statusRank(right.stat);
  });
}

function typeLabel(type) {
  if (type === "ddl") return "DDL";
  if (type === "remind") return ui("提醒", "Reminder");
  return ui("计划", "Plan");
}

function priorityLabel(priority) {
  if (priority === "high") return ui("高", "High");
  if (priority === "low") return ui("低", "Low");
  return ui("中", "Medium");
}

function statusLabel(status) {
  if (status === "done") return ui("完成", "Done");
  if (status === "cancelled") return ui("已取消", "Cancelled");
  return ui("待办", "To do");
}

function tagClass(value, kind) {
  if (kind === "type" && value === "ddl") return "purple";
  if (kind === "type" && value === "remind") return "orange";
  if (kind === "priority" && value === "high") return "red";
  if (kind === "priority" && value === "mid") return "orange";
  if (kind === "status" && value === "done") return "green";
  if (kind === "status" && value === "cancelled") return "gray";
  return "blue";
}

function empty(text) {
  return `<div class="empty">${esc(text)}</div>`;
}

function taskRow(event) {
  const view = eventView(event);
  return `<article class="task-row clickable status-${esc(event.stat || "todo")}" data-event-id="${esc(event.evtId)}" tabindex="0" role="button">
    <div>
      <div class="task-title">${esc(event.title)}</div>
      <div class="tags">
        <span class="tag ${tagClass(event.evtType, "type")}">${esc(typeLabel(event.evtType))}</span>
        <span class="tag ${tagClass(event.prio, "priority")}">${esc(priorityLabel(event.prio))}</span>
        <span class="tag ${tagClass(event.stat, "status")}">${esc(statusLabel(event.stat))}</span>
        <span class="tag ${view.overdue ? "red" : "blue"}">${esc(view.label)}</span>
      </div>
      ${event.desc ? `<p class="task-desc">${esc(event.desc)}</p>` : ""}
    </div>
  </article>`;
}

function ensureOverviewDeviceCard() {
  if ($("overviewPiState")) return;
  const summary = document.querySelector(".summary-grid");
  if (!summary) return;
  const section = document.createElement("section");
  section.className = "card overview-device-card";
  section.innerHTML = `<header><h2>${esc(ui("树莓派状态", "Raspberry Pi status"))}</h2><a class="link" href="/work/device">${esc(ui("设备详情", "Device details"))}</a></header><div class="card-body"><div class="device-status-main"><span class="device-state-dot" id="overviewPiDot"></span><div><div class="device-state-title" id="overviewPiState">${esc(ui("等待状态", "Waiting"))}</div><div class="row-meta" id="overviewPiSeen">—</div></div></div><div class="device-kv-grid"><div><span>${esc(ui("人物", "People"))}</span><strong id="overviewPiPersons">—</strong></div><div><span>${esc(ui("状态置信度", "Confidence"))}</span><strong id="overviewPiConfidence">—</strong></div><div><span>${esc(ui("是否有人", "Presence"))}</span><strong id="overviewPiPresent">—</strong></div></div></div>`;
  summary.insertAdjacentElement("afterend", section);
}

function renderOverviewDevice() {
  ensureOverviewDeviceCard();
  const latest = state.deviceStates.find((row) => row.deviceId === "pi") || null;
  const view = deviceStateView(latest);
  const dot = $("overviewPiDot");
  if (dot) dot.className = `device-state-dot ${view.state}`;
  if ($("overviewPiState")) $("overviewPiState").textContent = view.label;
  if ($("overviewPiSeen")) {
    $("overviewPiSeen").textContent = view.seenAt
      ? ui(`最后回传：${formatDateTime(view.seenAt)}`, `Last report: ${formatDateTime(view.seenAt)}`)
      : ui("尚未收到树莓派回传", "No Raspberry Pi report yet");
  }
  const names = view.persons.map((person) => person.name || person.personId).filter(Boolean);
  if ($("overviewPiPersons")) $("overviewPiPersons").textContent = names.length ? names.join("、") : ui("未识别", "None identified");
  if ($("overviewPiConfidence")) $("overviewPiConfidence").textContent = view.confidence == null ? "—" : `${Math.round(Number(view.confidence) * 100)}%`;
  if ($("overviewPiPresent")) $("overviewPiPresent").textContent = view.present && !view.stale ? ui("有人", "Present") : ui("无人", "Away");
}

function filteredEvents() {
  const query = String($("globalSearch")?.value || "").trim().toLowerCase();
  return state.events.filter((event) => {
    if (!["plan", "ddl", "remind"].includes(event.evtType)) return false;
    if (!query) return true;
    return `${event.title || ""} ${event.desc || ""} ${event.stTime || ""} ${event.endTime || ""} ${event.triggerTime || ""}`.toLowerCase().includes(query);
  });
}

function renderOverview() {
  const events = sortEvents(filteredEvents());
  const todos = events.filter((event) => event.stat === "todo");
  const today = events.filter((event) => eventView(event).today);
  const soon = todos.filter((event) => {
    if (event.evtType !== "ddl") return false;
    const view = eventView(event);
    if (!view.end) return false;
    const difference = view.end.getTime() - Date.now();
    return difference >= 0 && difference <= 72 * 3600_000;
  });
  const openIdeas = state.ideas.filter((idea) => !idea.handled);

  $("ovTodo").textContent = todos.length;
  $("ovToday").textContent = today.length;
  $("ovDeadline").textContent = soon.length;
  $("ovIdeas").textContent = openIdeas.length;
  $("overviewTasks").innerHTML = today.map(taskRow).join("") || empty(ui("暂无今日事项", "No events today"));
  $("overviewTimeline").innerHTML = soon.slice(0, 8).map(taskRow).join("") || empty(ui("72 小时内无 DDL", "No DDL in the next 72 hours"));
  $("overviewIdeas").innerHTML = openIdeas.slice(-5).reverse().map((idea) => `<div class="row-card"><div class="row-title">${esc(idea.content)}</div><div class="row-meta">${esc(idea.createdAt || "")}</div></div>`).join("") || empty(ui("暂无待整理灵感", "No unprocessed ideas"));
  renderOverviewDevice();
}

async function refreshOverview() {
  try {
    setApi("busy", ui("API 请求中", "API loading"));
    const [events, ideas, deviceStates] = await Promise.all([
      getData("/api/evt?includeReminders=true&includeCourseTemplates=false"),
      getData("/api/idea"),
      getData("/api/devState?devId=pi&limit=1"),
    ]);
    state.events = events;
    state.ideas = ideas;
    state.deviceStates = deviceStates;
    renderOverview();
    setApi("ok", ui("API 在线", "API online"));
    markRefresh();
  } catch (error) {
    setApi("err", ui("API 异常", "API error"));
    toast(error.message);
    renderOverview();
  }
}

function openEvent(eventId) {
  const event = state.events.find((item) => item.evtId === eventId);
  const start = event ? eventStartDate(event) : null;
  const dateParam = start && !Number.isNaN(start.getTime())
    ? `date=${encodeURIComponent(localDateValue(start))}&`
    : "";
  location.href = `/work/update?${dateParam}evtId=${encodeURIComponent(eventId)}`;
}

document.body.addEventListener("click", (event) => {
  const row = event.target.closest?.("[data-event-id]");
  if (row) openEvent(row.dataset.eventId);
});

document.body.addEventListener("keydown", (event) => {
  const row = event.target.closest?.("[data-event-id]");
  if (row && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    openEvent(row.dataset.eventId);
  }
});

$("globalSearch")?.addEventListener("input", renderOverview);
window.addEventListener("smartcore:languagechange", renderOverview);

ensureDeviceNav(false);
ensureOverviewDeviceCard();
refreshOverview();
setInterval(refreshOverview, 10000);
