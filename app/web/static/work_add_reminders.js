import { getUiLanguage } from "./work_shared.js";

const $ = (id) => document.getElementById(id);
const page = document.body.dataset.page;
const DEFAULT_REMINDERS = [
  { anchor: "start", offsetMin: 10, automatic: true },
  { anchor: "end", offsetMin: 10, automatic: true },
];

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

function planForm() {
  return $("planForm");
}

function normalizeSpec(raw = {}) {
  const anchor = String(raw.anchor || "start").toLowerCase() === "end" ? "end" : "start";
  const offset = Math.max(0, Math.min(10080, Number.parseInt(raw.offsetMin, 10) || 0));
  return { anchor, offsetMin: offset };
}

function extraReminderRows() {
  return Array.from(document.querySelectorAll("#planExtraReminderList [data-extra-reminder]"));
}

function collectExtraReminders() {
  const seen = new Set();
  return extraReminderRows().flatMap((row) => {
    const spec = normalizeSpec({
      anchor: row.querySelector('[name="reminderAnchor"]')?.value,
      offsetMin: row.querySelector('[name="reminderOffset"]')?.value,
    });
    const key = `${spec.anchor}:${spec.offsetMin}`;
    if (key === "start:10" || key === "end:10" || seen.has(key)) return [];
    seen.add(key);
    return [spec];
  });
}

function relativeLabel(spec) {
  const phase = spec.anchor === "start"
    ? ui("计划开始", "plan start")
    : ui("计划结束", "plan end");
  if (spec.offsetMin === 0) {
    return ui(`${phase}时`, `At ${phase}`);
  }
  return ui(`${phase}前 ${spec.offsetMin} 分钟`, `${spec.offsetMin} min before ${phase}`);
}

function reminderKindLabel(spec) {
  if (spec.automatic) return ui("自动提醒", "Automatic");
  return ui("额外提醒", "Additional");
}

function triggerTime(spec) {
  const form = planForm();
  const startValue = form?.elements.stTime?.value;
  if (!startValue) return null;
  const start = new Date(startValue);
  if (Number.isNaN(start.getTime())) return null;
  const duration = Math.max(1, Number(form.elements.durationMin?.value || 30));
  const anchor = spec.anchor === "end"
    ? new Date(start.getTime() + duration * 60000)
    : start;
  return new Date(anchor.getTime() - spec.offsetMin * 60000);
}

function formatTrigger(spec) {
  const trigger = triggerTime(spec);
  if (!trigger) return relativeLabel(spec);
  return trigger.toLocaleString(getUiLanguage() === "en" ? "en-US" : "zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function rowHtml(spec = { anchor: "start", offsetMin: 30 }) {
  const normalized = normalizeSpec(spec);
  return `
    <article class="plan-reminder-row" data-extra-reminder data-no-translate>
      <label class="field">
        <span data-reminder-label="anchor">${esc(ui("相对节点", "Relative to"))}</span>
        <select name="reminderAnchor">
          <option value="start" ${normalized.anchor === "start" ? "selected" : ""}>${esc(ui("计划开始", "Plan start"))}</option>
          <option value="end" ${normalized.anchor === "end" ? "selected" : ""}>${esc(ui("计划结束", "Plan end"))}</option>
        </select>
      </label>
      <label class="field">
        <span data-reminder-label="offset">${esc(ui("提前分钟数", "Minutes before"))}</span>
        <input name="reminderOffset" type="number" min="0" max="10080" value="${normalized.offsetMin}">
      </label>
      <button class="btn btn-danger plan-reminder-remove" type="button" data-remove-reminder>${esc(ui("移除", "Remove"))}</button>
    </article>`;
}

function ensureEditor() {
  const form = planForm();
  if (!form || $("planReminderEditor")) return;
  form.insertAdjacentHTML("beforeend", `
    <section class="plan-reminder-editor" id="planReminderEditor" data-no-translate>
      <div class="plan-reminder-heading">
        <div>
          <strong id="planReminderTitle">${esc(ui("提醒设置", "Reminder settings"))}</strong>
          <p id="planReminderHelp">${esc(ui(
            "每个计划固定生成开始前 10 分钟和结束前 10 分钟提醒，可继续添加额外提醒。",
            "Every plan automatically gets reminders 10 minutes before it starts and ends. Additional reminders can be added.",
          ))}</p>
        </div>
        <button class="btn" id="addPlanReminderBtn" type="button">${esc(ui("添加提醒", "Add reminder"))}</button>
      </div>
      <div class="plan-default-reminders" id="planDefaultReminders">
        <div class="plan-default-reminder"><span>${esc(ui("自动提醒", "Automatic"))}</span><strong>${esc(relativeLabel(DEFAULT_REMINDERS[0]))}</strong></div>
        <div class="plan-default-reminder"><span>${esc(ui("自动提醒", "Automatic"))}</span><strong>${esc(relativeLabel(DEFAULT_REMINDERS[1]))}</strong></div>
      </div>
      <div class="plan-extra-reminder-list" id="planExtraReminderList"></div>
    </section>
  `);
  $("addPlanReminderBtn")?.addEventListener("click", () => addReminderRow());
  form.addEventListener("input", renderReminderPreview);
  form.addEventListener("change", renderReminderPreview);
  form.addEventListener("reset", () => setTimeout(() => setExtraReminders([]), 0));
}

function addReminderRow(spec = { anchor: "start", offsetMin: 30 }) {
  ensureEditor();
  $("planExtraReminderList")?.insertAdjacentHTML("beforeend", rowHtml(spec));
  renderReminderPreview();
}

function setExtraReminders(specs) {
  ensureEditor();
  const list = $("planExtraReminderList");
  if (!list) return;
  list.innerHTML = "";
  (Array.isArray(specs) ? specs : []).forEach((spec) => addReminderRow(spec));
  renderReminderPreview();
}

function renderEditorLanguage() {
  if (!$("planReminderEditor")) return;
  $("planReminderTitle").textContent = ui("提醒设置", "Reminder settings");
  $("planReminderHelp").textContent = ui(
    "每个计划固定生成开始前 10 分钟和结束前 10 分钟提醒，可继续添加额外提醒。",
    "Every plan automatically gets reminders 10 minutes before it starts and ends. Additional reminders can be added.",
  );
  $("addPlanReminderBtn").textContent = ui("添加提醒", "Add reminder");
  const defaults = $("planDefaultReminders")?.children || [];
  Array.from(defaults).forEach((item, index) => {
    item.querySelector("span").textContent = ui("自动提醒", "Automatic");
    item.querySelector("strong").textContent = relativeLabel(DEFAULT_REMINDERS[index]);
  });
  extraReminderRows().forEach((row) => {
    row.querySelector('[data-reminder-label="anchor"]').textContent = ui("相对节点", "Relative to");
    row.querySelector('[data-reminder-label="offset"]').textContent = ui("提前分钟数", "Minutes before");
    const select = row.querySelector('[name="reminderAnchor"]');
    if (select) {
      select.options[0].textContent = ui("计划开始", "Plan start");
      select.options[1].textContent = ui("计划结束", "Plan end");
    }
    row.querySelector("[data-remove-reminder]").textContent = ui("移除", "Remove");
  });
}

function reminderPreviewHtml() {
  const reminders = [...DEFAULT_REMINDERS, ...collectExtraReminders()];
  return `
    <section class="preview-children plan-reminder-preview" id="planReminderPreview" data-no-translate>
      <div class="preview-children-title">${esc(ui("将生成的提醒", "Reminders to create"))}</div>
      ${reminders.map((spec) => `
        <div class="preview-child">
          <div>
            <strong>${esc(relativeLabel(spec))}</strong>
            <span>${esc(formatTrigger(spec))}</span>
          </div>
          <span class="tag ${spec.automatic ? "blue" : "green"}">${esc(reminderKindLabel(spec))}</span>
        </div>`).join("")}
    </section>`;
}

function renderReminderPreview() {
  if (page !== "add") return;
  const root = $("createPreview");
  if (!root || !planForm()?.classList.contains("active")) return;
  const current = $("planReminderPreview");
  const signature = JSON.stringify({
    language: getUiLanguage(),
    start: planForm().elements.stTime?.value || "",
    duration: planForm().elements.durationMin?.value || "",
    reminders: collectExtraReminders(),
  });
  if (current?.dataset.signature === signature) return;
  current?.remove();
  root.insertAdjacentHTML("beforeend", reminderPreviewHtml());
  $("planReminderPreview").dataset.signature = signature;
}

function installPreviewObserver() {
  const root = $("createPreview");
  if (!root) return;
  const observer = new MutationObserver(() => {
    if (planForm()?.classList.contains("active")) renderReminderPreview();
  });
  observer.observe(root, { childList: true });
}

function installFetchBridge() {
  if (window.__smartcoreReminderFetchInstalled) return;
  window.__smartcoreReminderFetchInstalled = true;
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (input, init = undefined) => {
    const url = typeof input === "string" ? input : input?.url || "";
    const method = String(init?.method || (typeof input !== "string" ? input?.method : "GET") || "GET").toUpperCase();
    let nextInit = init;

    if (method === "POST" && url.includes("/api/planEvt") && typeof init?.body === "string") {
      try {
        const payload = JSON.parse(init.body);
        payload.extraReminders = collectExtraReminders();
        nextInit = { ...init, body: JSON.stringify(payload) };
      } catch {
        // Preserve the original request so the API can return its normal validation error.
      }
    }

    const response = await nativeFetch(input, nextInit);
    if (method === "POST" && url.includes("/api/llm/parse")) {
      response.clone().json().then((body) => {
        const parsed = body?.data?.parsed;
        const eventType = String(parsed?.evtType || parsed?.tab || "").toLowerCase();
        if (eventType === "plan") {
          setTimeout(() => setExtraReminders(parsed.extraReminders || parsed.reminders || []), 0);
        }
      }).catch(() => {});
    }
    if (method === "POST" && url.includes("/api/planEvt") && response.ok) {
      setTimeout(() => setExtraReminders([]), 0);
    }
    return response;
  };
}

function bindDelegation() {
  document.body.addEventListener("click", (event) => {
    const remove = event.target.closest?.("[data-remove-reminder]");
    if (!remove) return;
    remove.closest("[data-extra-reminder]")?.remove();
    renderReminderPreview();
  });
  document.querySelectorAll("[data-create-tab]").forEach((button) => {
    button.addEventListener("click", () => setTimeout(renderReminderPreview, 0));
  });
}

if (page === "add") {
  ensureEditor();
  installFetchBridge();
  installPreviewObserver();
  bindDelegation();
  renderEditorLanguage();
  renderReminderPreview();
  window.addEventListener("smartcore:languagechange", () => {
    renderEditorLanguage();
    renderReminderPreview();
  });
}
