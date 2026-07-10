import { getUiLanguage } from "./work_shared.js";

const page = document.body.dataset.page;
const $ = (id) => document.getElementById(id);
let decorateTimer = null;
let latestRequest = 0;

function ui(zh, en) {
  return getUiLanguage() === "en" ? en : zh;
}

function statusLabel(status) {
  if (status === "done") return ui("完成", "Done");
  if (status === "cancelled") return ui("已取消", "Cancelled");
  return ui("待办", "To do");
}

function statusClass(status) {
  if (status === "done") return "green";
  if (status === "cancelled") return "gray";
  return "blue";
}

async function decorateUpdateRows() {
  if (page !== "update") return;
  const list = $("evtList");
  const date = $("evtDateFilter")?.value;
  if (!list || !date || !list.querySelector("[data-event-id]")) return;

  const requestId = ++latestRequest;
  try {
    const response = await fetch(
      `/api/evt?date=${encodeURIComponent(date)}&includeReminders=true&includeCourseTemplates=false`,
      { cache: "no-store" },
    );
    const body = await response.json();
    if (!response.ok || body.ok === false || requestId !== latestRequest) return;
    const events = new Map((body.data || []).map((event) => [event.evtId, event]));

    list.querySelectorAll("[data-event-id]").forEach((row) => {
      const event = events.get(row.dataset.eventId);
      if (!event) return;
      const rowStatus = event.stat || "todo";
      const desiredRowClass = `status-${rowStatus}`;
      if (!row.classList.contains(desiredRowClass)) {
        row.classList.remove("status-todo", "status-done", "status-cancelled");
        row.classList.add(desiredRowClass);
      }
      const tags = row.querySelector(".tags");
      if (!tags) return;
      let badge = tags.querySelector("[data-event-status]");
      if (!badge) {
        badge = document.createElement("span");
        badge.dataset.eventStatus = "";
        tags.appendChild(badge);
      }
      const desiredBadgeClass = `tag ${statusClass(rowStatus)}`;
      const desiredLabel = statusLabel(rowStatus);
      if (badge.className !== desiredBadgeClass) badge.className = desiredBadgeClass;
      if (badge.textContent !== desiredLabel) badge.textContent = desiredLabel;
    });
  } catch {
    // The primary Update Event request remains authoritative; decoration is optional.
  }
}

function scheduleDecorate() {
  clearTimeout(decorateTimer);
  decorateTimer = setTimeout(decorateUpdateRows, 30);
}

function initializeUpdateVisibility() {
  if (page !== "update") return;
  const filter = $("evtStatusFilter");
  if (filter) {
    filter.value = "all";
    filter.dispatchEvent(new Event("change", { bubbles: true }));
  }

  const list = $("evtList");
  if (list) {
    new MutationObserver(scheduleDecorate).observe(list, { childList: true, subtree: true });
  }
  $("evtDateFilter")?.addEventListener("change", scheduleDecorate);
  $("evtStatusFilter")?.addEventListener("change", scheduleDecorate);
  window.addEventListener("smartcore:languagechange", scheduleDecorate);
  scheduleDecorate();
}

initializeUpdateVisibility();
