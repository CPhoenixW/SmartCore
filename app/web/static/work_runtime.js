import { setUiLanguage, t } from "./work_shared.js";
import "./work_relation_i18n.js";

const page = document.body.dataset.page;
const $ = (id) => document.getElementById(id);

function ensureInteractionStyles() {
  if (document.querySelector('link[href="/static/work/work_interaction_fixes.css"]')) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "/static/work/work_interaction_fixes.css";
  document.head.appendChild(link);
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;");
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
  el.textContent = t(text);
}

function avatarText(name) {
  const value = String(name || "SC").trim();
  return value.slice(0, 2).toUpperCase() || "SC";
}

async function loadTopUser() {
  try {
    const response = await fetch("/api/user/me", { cache: "no-store" });
    const body = await response.json();
    const user = body.data || {};
    const text = $("topAvatarText");
    const image = $("topAvatarImg");
    if (text) text.textContent = avatarText(user.displayName);
    if (image && user.avatarUrl) {
      image.src = user.avatarUrl;
      image.hidden = false;
      if (text) text.hidden = true;
    }
  } catch {
    // User data is supplementary; do not delay the page.
  }
}

function logSearchText(row) {
  return Object.entries(row || {})
    .map(([key, value]) => `${key}:${typeof value === "object" ? JSON.stringify(value) : value ?? ""}`)
    .join(" ")
    .toLowerCase();
}

function logTitle(row, tab) {
  if (tab === "act") return `${row.action || t("操作日志")} · ${row.targetKind || "target"}`;
  if (tab === "notify") return `${row.title || t("提醒")} · ${row.channel || "channel"}`;
  return `${row.intent || row.channel || t("消息")}`;
}

function logMeta(row) {
  return [
    row.createdAt || row.scheduledAt || row.sentAt || "",
    row.result || row.stat || row.direction || "",
    row.targetId || row.evtId || row.externalId || row.msgId || row.notifyId || row.actId || "",
  ].filter(Boolean).join(" · ");
}

function initFastLogs() {
  if (page !== "log") return;
  const list = $("logList");
  if (!list) return;
  const runtime = {
    tab: "act",
    logs: { act: [], notify: [], msg: [] },
    loaded: false,
    restoreQueued: false,
  };
  let observer = null;

  function observeList() {
    observer?.observe(list, { childList: true });
  }

  function filteredRows() {
    const query = $("logKeyword")?.value.trim().toLowerCase() || "";
    const status = $("logStatusFilter")?.value || "";
    return (runtime.logs[runtime.tab] || []).filter((row) => {
      if (query && !logSearchText(row).includes(query)) return false;
      if (status && row.stat !== status && row.result !== status) return false;
      return true;
    });
  }

  function render() {
    observer?.disconnect();
    const rows = filteredRows();
    list.innerHTML = rows.length
      ? rows.map((row) => `<details class="log-row"><summary><span class="row-title">${esc(logTitle(row, runtime.tab))}</span><span class="row-meta">${esc(logMeta(row))}</span></summary><pre class="log-json">${esc(JSON.stringify(row, null, 2))}</pre></details>`).join("")
      : `<div class="empty">${runtime.loaded ? t("暂无日志") : t("正在加载日志...")}</div>`;
    observeList();
  }

  observer = new MutationObserver(() => {
    if (!runtime.loaded || runtime.restoreQueued) return;
    runtime.restoreQueued = true;
    queueMicrotask(() => {
      runtime.restoreQueued = false;
      render();
    });
  });
  observeList();

  document.querySelectorAll("[data-log-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      runtime.tab = button.dataset.logTab;
      document.querySelectorAll("[data-log-tab]").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      render();
    });
  });
  $("logKeyword")?.addEventListener("input", render);
  $("logStatusFilter")?.addEventListener("change", render);
  window.addEventListener("smartcore:languagechange", render);

  render();
  setApi("busy", "API 请求中");
  fetch("/api/log?limit=120")
    .then(async (response) => {
      const body = await response.json();
      if (!response.ok || body.ok === false) throw new Error(body.detail || `HTTP ${response.status}`);
      runtime.logs = body.data || runtime.logs;
      runtime.loaded = true;
      render();
      setApi("ok", "API 在线");
      if ($("lastRefresh")) {
        $("lastRefresh").textContent = `${t("更新于")} ${new Date().toLocaleTimeString(undefined, { hour12: false })}`;
      }
    })
    .catch((error) => {
      runtime.loaded = true;
      observer?.disconnect();
      setApi("err", "API 异常");
      list.innerHTML = `<div class="empty">${esc(error.message || "Log loading failed")}</div>`;
    });
}

function initCompleteSettingsSave() {
  if (page !== "settings") return;
  const form = $("userSettingsForm");
  if (!form) return;

  fetch("/api/user/me", { cache: "no-store" })
    .then((response) => response.json())
    .then((body) => {
      const user = body.data || {};
      if (form.elements.reminderChannel) {
        form.elements.reminderChannel.value = user.reminderChannel || "screen";
      }
      if (form.elements.language) {
        form.elements.language.value = user.language || "zh";
      }
    })
    .catch(() => {});

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
    const body = {
      displayName: form.elements.displayName.value.trim(),
      language: form.elements.language.value,
      avatarUrl: form.elements.avatarUrl.value.trim() || null,
      reminderChannel: form.elements.reminderChannel.value,
    };
    if (!body.displayName) return toast(body.language === "en" ? "Display name is required" : "用户名称不能为空");
    try {
      setApi("busy", "API 请求中");
      const response = await fetch("/api/user/me", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok || result.ok === false) throw new Error(result.detail || `HTTP ${response.status}`);
      setUiLanguage(body.language);
      setApi("ok", "API 在线");
      toast(t("设置已保存"));
      const text = $("topAvatarText");
      const image = $("topAvatarImg");
      if (text) text.textContent = avatarText(body.displayName);
      if (image && body.avatarUrl) {
        image.src = body.avatarUrl;
        image.hidden = false;
        if (text) text.hidden = true;
      } else if (image) {
        image.hidden = true;
        image.removeAttribute("src");
        if (text) text.hidden = false;
      }
    } catch (error) {
      setApi("err", "API 异常");
      toast(error.message || "Save failed");
    }
  }, true);
}

ensureInteractionStyles();
loadTopUser();
initFastLogs();
initCompleteSettingsSave();
