import { setUiLanguage } from "./work_shared.js";

const page = document.body.dataset.page;
const $ = (id) => document.getElementById(id);

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
  el.textContent = text;
}

function logSearchText(row) {
  return Object.entries(row || {})
    .map(([key, value]) => `${key}:${typeof value === "object" ? JSON.stringify(value) : value ?? ""}`)
    .join(" ")
    .toLowerCase();
}

function logTitle(row, tab) {
  if (tab === "act") return `${row.action || "操作"} · ${row.targetKind || "target"}`;
  if (tab === "notify") return `${row.title || "提醒"} · ${row.channel || "channel"}`;
  return `${row.intent || row.channel || "消息"}`;
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
  const runtime = { tab: "act", logs: { act: [], notify: [], msg: [] } };

  function render() {
    const list = $("logList");
    if (!list) return;
    const query = $("logKeyword")?.value.trim().toLowerCase() || "";
    const status = $("logStatusFilter")?.value || "";
    const rows = (runtime.logs[runtime.tab] || []).filter((row) => {
      if (query && !logSearchText(row).includes(query)) return false;
      if (status && row.stat !== status && row.result !== status) return false;
      return true;
    });
    list.innerHTML = rows.length
      ? rows.map((row) => `<details class="log-row"><summary><span class="row-title">${esc(logTitle(row, runtime.tab))}</span><span class="row-meta">${esc(logMeta(row))}</span></summary><pre class="log-json">${esc(JSON.stringify(row, null, 2))}</pre></details>`).join("")
      : '<div class="empty">暂无日志</div>';
  }

  document.querySelectorAll("[data-log-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      runtime.tab = button.dataset.logTab;
      render();
    });
  });
  $("logKeyword")?.addEventListener("input", render);
  $("logStatusFilter")?.addEventListener("change", render);

  setApi("busy", "API 请求中");
  fetch("/api/log?limit=120")
    .then(async (response) => {
      const body = await response.json();
      if (!response.ok || body.ok === false) throw new Error(body.detail || `HTTP ${response.status}`);
      runtime.logs = body.data || runtime.logs;
      render();
      setApi("ok", "API 在线");
      if ($("lastRefresh")) {
        $("lastRefresh").textContent = "更新于 " + new Date().toLocaleTimeString("zh-CN", { hour12: false });
      }
    })
    .catch((error) => {
      setApi("err", "API 异常");
      $("logList").innerHTML = `<div class="empty">${esc(error.message || "日志加载失败")}</div>`;
    });
}

function initCompleteSettingsSave() {
  if (page !== "settings") return;
  const form = $("userSettingsForm");
  if (!form) return;

  fetch("/api/user/me")
    .then((response) => response.json())
    .then((body) => {
      const user = body.data || {};
      if (form.elements.reminderChannel) {
        form.elements.reminderChannel.value = user.reminderChannel || "screen";
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
    if (!body.displayName) return toast("用户名称不能为空");
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
      toast(body.language === "en" ? "Settings saved" : "设置已保存");
      const avatarText = $("topAvatarText");
      const avatarImg = $("topAvatarImg");
      if (avatarText) avatarText.textContent = body.displayName.slice(0, 2).toUpperCase();
      if (avatarImg && body.avatarUrl) {
        avatarImg.src = body.avatarUrl;
        avatarImg.hidden = false;
        if (avatarText) avatarText.hidden = true;
      }
    } catch (error) {
      setApi("err", "API 异常");
      toast(error.message || "保存失败");
    }
  }, true);
}

initFastLogs();
initCompleteSettingsSave();
