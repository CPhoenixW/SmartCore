import { getUiLanguage } from "./work_shared.js";

const $ = (id) => document.getElementById(id);
const page = document.body.dataset.page;
let reminderActive = false;
let previewQueued = false;
let manualCounter = 0;

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

function toLocal(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (part) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function displayTime(value) {
  if (!value) return ui("未设置", "Not set");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(getUiLanguage() === "en" ? "en-US" : "zh-CN", { hour12: false });
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

function ensureReminderForm() {
  const tabs = document.querySelector(".tabs");
  const ddlForm = $("ddlForm");
  if (!tabs || !ddlForm || $("remindForm")) return;
  const ddlTab = tabs.querySelector('[data-create-tab="ddl"]');
  ddlTab?.insertAdjacentHTML(
    "beforebegin",
    `<button class="tab" type="button" data-create-tab="remind" data-no-translate>${esc(ui("提醒事项", "Reminder"))}</button>`,
  );
  ddlForm.insertAdjacentHTML(
    "beforebegin",
    `<form id="remindForm" class="form-pane" data-endpoint="/api/remindEvt" data-no-translate>
      <label class="field required"><span data-remind-label="title">${esc(ui("标题", "Title"))}</span><input name="title" required placeholder="${esc(ui("例如：带学生证", "Example: Bring student ID"))}"></label>
      <label class="field"><span data-remind-label="desc">${esc(ui("描述", "Description"))}</span><textarea name="desc" rows="3"></textarea></label>
      <label class="field required"><span data-remind-label="time">${esc(ui("提醒时间", "Reminder time"))}</span><input name="triggerTime" type="datetime-local" required></label>
      <label class="field"><span data-remind-label="prio">${esc(ui("优先级", "Priority"))}</span><select name="prio"><option value="mid">${esc(ui("中", "Medium"))}</option><option value="high">${esc(ui("高", "High"))}</option><option value="low">${esc(ui("低", "Low"))}</option></select></label>
    </form>`,
  );
  $("remindForm")?.addEventListener("input", schedulePreview);
  $("remindForm")?.addEventListener("change", schedulePreview);
}

function activateReminder() {
  reminderActive = true;
  document.querySelectorAll("[data-create-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.createTab === "remind");
  });
  $("planForm")?.classList.remove("active");
  $("ddlForm")?.classList.remove("active");
  $("remindForm")?.classList.add("active");
  const submit = $("createSubmitBtn");
  if (submit) submit.textContent = ui("创建提醒事项", "Create reminder");
  schedulePreview();
}

function leaveReminder() {
  reminderActive = false;
  $("remindForm")?.classList.remove("active");
  schedulePreview();
}

function reminderPayload() {
  const form = $("remindForm");
  return {
    title: form?.elements.title?.value.trim() || "",
    desc: form?.elements.desc?.value.trim() || null,
    triggerTime: toIso(form?.elements.triggerTime?.value || ""),
    prio: form?.elements.prio?.value || "mid",
  };
}

async function submitReminder() {
  const payload = reminderPayload();
  if (!payload.title) return toast(ui("请填写标题", "Enter a title"));
  if (!payload.triggerTime) return toast(ui("请设置提醒时间", "Set the reminder time"));
  try {
    setApi("busy", ui("API 请求中", "API loading"));
    const response = await fetch("/api/remindEvt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body.ok === false) throw new Error(body.detail || `HTTP ${response.status}`);
    $("remindForm")?.reset();
    setApi("ok", ui("API 在线", "API online"));
    toast(ui("提醒事项已创建", "Reminder created"));
    schedulePreview();
  } catch (error) {
    setApi("err", ui("API 异常", "API error"));
    toast(error.message || ui("创建失败", "Create failed"));
  }
}

function manualRowHtml(plan = {}) {
  manualCounter += 1;
  return `<article class="ddl-manual-plan-row" data-ddl-manual-plan data-no-translate>
    <input name="planEvtId" type="hidden" value="${esc(plan.planEvtId || plan.evtId || "")}">
    <label class="field"><span>${esc(ui("计划标题", "Plan title"))}</span><input name="title" value="${esc(plan.title || "")}" placeholder="${esc(ui(`关联计划 ${manualCounter}`, `Linked plan ${manualCounter}`))}"></label>
    <label class="field required"><span>${esc(ui("开始时间", "Start time"))}</span><input name="stTime" type="datetime-local" required value="${esc(toLocal(plan.stTime))}"></label>
    <label class="field"><span>${esc(ui("持续时间（分钟）", "Duration (minutes)"))}</span><input name="durationMin" type="number" min="1" value="${esc(plan.durationMin || 30)}"></label>
    <button class="btn btn-danger ddl-manual-remove" type="button" data-remove-ddl-plan>${esc(ui("移除", "Remove"))}</button>
  </article>`;
}

function ensureDdlMultipleEditor() {
  const editor = document.querySelector("#ddlForm .ddl-plan-editor");
  if (!editor || $("ddlManualPlanList")) return;
  editor.querySelector(".ddl-plan-heading")?.insertAdjacentHTML(
    "beforeend",
    `<button class="btn" id="addDdlPlanBtn" type="button" data-no-translate>${esc(ui("添加关联计划", "Add linked plan"))}</button>`,
  );
  editor.insertAdjacentHTML(
    "beforeend",
    `<div class="ddl-manual-plan-list" id="ddlManualPlanList"></div>`,
  );
  $("addDdlPlanBtn")?.addEventListener("click", () => addManualPlan());
  $("ddlForm")?.addEventListener("input", schedulePreview);
  $("ddlForm")?.addEventListener("change", schedulePreview);
}

function addManualPlan(plan = {}) {
  ensureDdlMultipleEditor();
  $("ddlManualPlanList")?.insertAdjacentHTML("beforeend", manualRowHtml(plan));
  schedulePreview();
}

function staticDdlPlans() {
  const form = $("ddlForm");
  if (!form) return [];
  const configs = [
    { role: "one_day_before", enabled: "oneDayEnabled", time: "oneDayTime", duration: "oneDayDuration", order: 0 },
    { role: "one_hour_before", enabled: "oneHourEnabled", time: "oneHourTime", duration: "oneHourDuration", order: 1 },
  ];
  return configs.flatMap((config) => {
    if (!form.elements[config.enabled]?.checked) return [];
    return [{
      planRole: config.role,
      stTime: toIso(form.elements[config.time]?.value || ""),
      durationMin: Number(form.elements[config.duration]?.value || 30),
      sortOrder: config.order,
    }];
  });
}

function manualDdlPlans() {
  return Array.from(document.querySelectorAll("[data-ddl-manual-plan]")).map((row, index) => ({
    planEvtId: row.querySelector('[name="planEvtId"]')?.value || undefined,
    planRole: "manual",
    title: row.querySelector('[name="title"]')?.value.trim() || undefined,
    stTime: toIso(row.querySelector('[name="stTime"]')?.value || ""),
    durationMin: Number(row.querySelector('[name="durationMin"]')?.value || 30),
    sortOrder: staticDdlPlans().length + index,
  }));
}

function collectDdlPlans() {
  return [...staticDdlPlans(), ...manualDdlPlans()];
}

function setDdlPlans(plans) {
  ensureDdlMultipleEditor();
  const form = $("ddlForm");
  const list = $("ddlManualPlanList");
  if (!form || !list || !Array.isArray(plans)) return;
  list.innerHTML = "";
  manualCounter = 0;
  const used = new Set();
  const assignStatic = (role, enabledName, timeName, durationName) => {
    const index = plans.findIndex((plan, planIndex) => !used.has(planIndex) && plan.planRole === role);
    const enabled = index >= 0;
    form.elements[enabledName].checked = enabled;
    if (enabled) {
      used.add(index);
      form.elements[timeName].value = toLocal(plans[index].stTime);
      form.elements[durationName].value = plans[index].durationMin || 30;
    }
  };
  assignStatic("one_day_before", "oneDayEnabled", "oneDayTime", "oneDayDuration");
  assignStatic("one_hour_before", "oneHourEnabled", "oneHourTime", "oneHourDuration");
  plans.forEach((plan, index) => {
    if (!used.has(index)) addManualPlan(plan);
  });
  schedulePreview();
}

function reminderPreview() {
  const payload = reminderPayload();
  return `<div class="preview-card ${payload.title ? "" : "empty-preview"}" data-no-translate>
    <div class="preview-title">${esc(payload.title || ui("等待填写标题", "Enter a title"))}</div>
    <div class="tags"><span class="tag orange">${esc(ui("提醒", "Reminder"))}</span><span class="tag blue">${esc(displayTime(payload.triggerTime))}</span></div>
    ${payload.desc ? `<p class="preview-desc">${esc(payload.desc)}</p>` : ""}
  </div>`;
}

function ddlPlansPreview() {
  const plans = collectDdlPlans();
  return `<section class="preview-children ddl-all-plan-preview" data-no-translate>
    <div class="preview-children-title">${esc(ui("同时创建的计划", "Plans to create"))}</div>
    ${plans.length ? plans.map((plan, index) => `<div class="preview-child"><div><strong>${esc(plan.title || ui(`关联计划 ${index + 1}`, `Linked plan ${index + 1}`))}</strong><span>${esc(displayTime(plan.stTime))}</span></div><span class="tag green">${esc(ui(`${plan.durationMin} 分钟`, `${plan.durationMin} min`))}</span></div>`).join("") : `<div class="empty compact-empty">${esc(ui("未启用关联计划", "No linked plans enabled"))}</div>`}
  </section>`;
}

function renderPreview() {
  previewQueued = false;
  const root = $("createPreview");
  if (!root) return;
  if (reminderActive) {
    root.innerHTML = reminderPreview();
    return;
  }
  if (!$("ddlForm")?.classList.contains("active")) return;
  root.querySelectorAll(".preview-children").forEach((element) => element.remove());
  root.insertAdjacentHTML("beforeend", ddlPlansPreview());
}

function schedulePreview() {
  if (previewQueued) return;
  previewQueued = true;
  queueMicrotask(renderPreview);
}

function installPreviewObserver() {
  const root = $("createPreview");
  if (!root) return;
  new MutationObserver(() => schedulePreview()).observe(root, { childList: true, subtree: false });
}

function applyParsed(parsed) {
  const type = String(parsed?.evtType || parsed?.tab || "").toLowerCase();
  if (type === "remind" || type === "reminder") {
    activateReminder();
    const form = $("remindForm");
    form.elements.title.value = parsed.title || "";
    form.elements.desc.value = parsed.desc || parsed.description || "";
    form.elements.triggerTime.value = toLocal(parsed.triggerTime || parsed.remindAt || parsed.at);
    form.elements.prio.value = parsed.prio || "mid";
    schedulePreview();
    return;
  }
  if (type === "ddl" && Array.isArray(parsed.plans)) {
    setDdlPlans(parsed.plans);
  }
}

function installFetchBridge() {
  if (window.__smartcoreEventRelationBridgeInstalled) return;
  window.__smartcoreEventRelationBridgeInstalled = true;
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (input, init = undefined) => {
    const url = typeof input === "string" ? input : input?.url || "";
    const method = String(init?.method || (typeof input !== "string" ? input?.method : "GET") || "GET").toUpperCase();
    let nextInit = init;
    if (method === "POST" && url.includes("/api/ddlEvt") && typeof init?.body === "string") {
      try {
        const payload = JSON.parse(init.body);
        payload.plans = collectDdlPlans();
        nextInit = { ...init, body: JSON.stringify(payload) };
      } catch {
        // Preserve original request and normal API validation.
      }
    }
    const response = await nativeFetch(input, nextInit);
    if (method === "POST" && url.includes("/api/llm/parse")) {
      response.clone().json().then((body) => {
        setTimeout(() => applyParsed(body?.data?.parsed || {}), 0);
      }).catch(() => {});
    }
    if (method === "POST" && url.includes("/api/ddlEvt") && response.ok) {
      setTimeout(() => {
        $("ddlManualPlanList").innerHTML = "";
        manualCounter = 0;
        schedulePreview();
      }, 0);
    }
    return response;
  };
}

function translateDynamicUi() {
  const remindTab = document.querySelector('[data-create-tab="remind"]');
  if (remindTab) remindTab.textContent = ui("提醒事项", "Reminder");
  const form = $("remindForm");
  if (form) {
    form.querySelector('[data-remind-label="title"]').textContent = ui("标题", "Title");
    form.querySelector('[data-remind-label="desc"]').textContent = ui("描述", "Description");
    form.querySelector('[data-remind-label="time"]').textContent = ui("提醒时间", "Reminder time");
    form.querySelector('[data-remind-label="prio"]').textContent = ui("优先级", "Priority");
    form.elements.title.placeholder = ui("例如：带学生证", "Example: Bring student ID");
    const labels = [["mid", "中", "Medium"], ["high", "高", "High"], ["low", "低", "Low"]];
    labels.forEach(([value, zh, en]) => { form.elements.prio.querySelector(`option[value="${value}"]`).textContent = ui(zh, en); });
  }
  if ($("addDdlPlanBtn")) $("addDdlPlanBtn").textContent = ui("添加关联计划", "Add linked plan");
  if (reminderActive && $("createSubmitBtn")) $("createSubmitBtn").textContent = ui("创建提醒事项", "Create reminder");
  schedulePreview();
}

function bind() {
  document.querySelector('[data-create-tab="remind"]')?.addEventListener("click", activateReminder);
  document.querySelectorAll('[data-create-tab="plan"], [data-create-tab="ddl"]').forEach((button) => {
    button.addEventListener("click", () => {
      leaveReminder();
      setTimeout(schedulePreview, 0);
    });
  });
  $("createSubmitBtn")?.addEventListener("click", (event) => {
    if (!reminderActive) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    submitReminder();
  }, true);
  $("remindForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    submitReminder();
  });
  document.body.addEventListener("click", (event) => {
    const remove = event.target.closest?.("[data-remove-ddl-plan]");
    if (!remove) return;
    remove.closest("[data-ddl-manual-plan]")?.remove();
    schedulePreview();
  });
  window.addEventListener("smartcore:languagechange", translateDynamicUi);
}

if (page === "add") {
  ensureReminderForm();
  ensureDdlMultipleEditor();
  installFetchBridge();
  installPreviewObserver();
  bind();
  translateDynamicUi();
  schedulePreview();
}
