import { ensureDeviceNav } from "./work_shared.js";

const page = document.body.dataset.page;
const $ = (id) => document.getElementById(id);
const state = {
  ideas: [],
  courses: [],
  logs: { act: [], notify: [], msg: [] },
  logTab: "act",
  createTab: "plan",
  user: null,
  selectedIdeaId: null,
};
const prioLabels = { high: "高", mid: "中", low: "低" };
const languageLabels = { zh: "中文", en: "English" };
const ddlPlanLabels = { one_day_before: "提前一天计划", one_hour_before: "提前一小时计划" };

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

async function apiGetQuiet(path) {
  const resp = await fetch(path);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || data.ok === false) throw new Error(data.detail || data.msg || `HTTP ${resp.status}`);
  return data.data;
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

function formVal(form, name) {
  return form?.elements[name]?.value?.trim() || "";
}

function numOrNull(value) {
  return value === "" || value == null ? null : Number(value);
}

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

function toLocalInputValue(value) {
  if (!value) return "";
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function displayLocal(value) {
  if (!value) return "未设置";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.replace("T", " ");
  return date.toLocaleString("zh-CN", { hour12: false });
}

function rowEmpty(text) {
  return `<div class="empty">${esc(text)}</div>`;
}

function tagClass(value) {
  if (value === "high") return "red";
  if (value === "mid") return "orange";
  return "blue";
}

function normalizePrio(value, fallbackTab = "plan") {
  const text = String(value || "").trim().toLowerCase();
  if (["high", "高", "urgent", "important", "紧急", "重要"].includes(text)) return "high";
  if (["low", "低", "later", "不急", "不重要"].includes(text)) return "low";
  if (["mid", "middle", "medium", "normal", "普通", "中"].includes(text)) return "mid";
  return fallbackTab === "ddl" ? "high" : "mid";
}

function normalizeTab(parsed) {
  const raw = String(parsed?.tab || parsed?.evtType || parsed?.type || "plan").trim().toLowerCase();
  return ["ddl", "deadline", "截止", "截止事项"].includes(raw) ? "ddl" : "plan";
}

function normalizeParsed(raw) {
  const p = raw || {};
  const tab = normalizeTab(p);
  const result = {
    tab,
    title: String(p.title || "").trim(),
    desc: String(p.desc ?? p.description ?? "").trim(),
    prio: normalizePrio(p.prio || p.priority, tab),
    durationMin: Number(p.durationMin || p.duration || 30),
    hardDdl: Boolean(p.hardDdl),
  };
  if (tab === "ddl") result.endTime = toLocalInputValue(p.endTime || p.deadline || p.at);
  else result.stTime = toLocalInputValue(p.stTime || p.startTime || p.at);
  return result;
}

function avatarText(name) {
  const text = String(name || "SC").trim();
  return text.slice(0, 2).toUpperCase() || "SC";
}

function applyAvatar(textId, imgId, user) {
  const img = $(imgId);
  const text = $(textId);
  if (!img || !text) return;
  text.textContent = avatarText(user?.displayName);
  if (user?.avatarUrl) {
    img.src = user.avatarUrl;
    img.hidden = false;
    text.hidden = true;
  } else {
    img.removeAttribute("src");
    img.hidden = true;
    text.hidden = false;
  }
}

function updateSettingsPreview() {
  const form = $("userSettingsForm");
  if (!form) return;
  const user = {
    displayName: formVal(form, "displayName") || "默认用户",
    language: formVal(form, "language") || "zh",
    avatarUrl: formVal(form, "avatarUrl") || null,
  };
  applyAvatar("settingsAvatarText", "settingsAvatarImg", user);
  if ($("settingsNamePreview")) $("settingsNamePreview").textContent = user.displayName;
  if ($("settingsLanguagePreview")) $("settingsLanguagePreview").textContent = languageLabels[user.language] || user.language;
}

function applyUserUI(user) {
  state.user = user;
  applyAvatar("topAvatarText", "topAvatarImg", user);
  const form = $("userSettingsForm");
  if (form) {
    form.elements.displayName.value = user.displayName || "";
    form.elements.language.value = user.language || "zh";
    form.elements.avatarUrl.value = user.avatarUrl || "";
    updateSettingsPreview();
  }
}

async function loadCurrentUser() {
  try {
    applyUserUI(await apiGetQuiet("/api/user/me"));
  } catch {
    applyUserUI({ displayName: "SC", language: "zh", avatarUrl: null });
  }
}

async function saveSettings(ev) {
  ev.preventDefault();
  const form = ev.currentTarget;
  const body = {
    displayName: formVal(form, "displayName"),
    language: formVal(form, "language") || "zh",
    avatarUrl: formVal(form, "avatarUrl") || null,
  };
  try {
    applyUserUI(await apiSend("/api/user/me", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }));
    toast("设置已保存");
  } catch (err) {
    toast(err.message);
  }
}

function ensureDdlPlanEditor() {
  const form = $("ddlForm");
  if (!form || form.querySelector(".ddl-plan-editor")) return;
  form.insertAdjacentHTML("beforeend", `
    <section class="ddl-plan-editor">
      <div class="ddl-plan-heading"><div><strong>关联计划</strong><p>默认提前一天和提前一小时，可关闭或调整具体时间。</p></div></div>
      <article class="ddl-plan-row" data-plan-role="one_day_before">
        <label class="check-line ddl-plan-toggle"><input type="checkbox" name="oneDayEnabled" checked><span>提前一天</span></label>
        <label class="field"><span>开始时间</span><input type="datetime-local" name="oneDayTime"></label>
        <label class="field"><span>持续时间（分钟）</span><input type="number" name="oneDayDuration" min="1" value="30"></label>
      </article>
      <article class="ddl-plan-row" data-plan-role="one_hour_before">
        <label class="check-line ddl-plan-toggle"><input type="checkbox" name="oneHourEnabled" checked><span>提前一小时</span></label>
        <label class="field"><span>开始时间</span><input type="datetime-local" name="oneHourTime"></label>
        <label class="field"><span>持续时间（分钟）</span><input type="number" name="oneHourDuration" min="1" value="30"></label>
      </article>
    </section>
  `);
}

function syncDdlPlanDefaults(force = false) {
  const form = $("ddlForm");
  if (!form) return;
  const endValue = formVal(form, "endTime");
  if (!endValue) return;
  const end = new Date(endValue);
  if (Number.isNaN(end.getTime())) return;
  const values = {
    oneDayTime: new Date(end.getTime() - 24 * 3600_000),
    oneHourTime: new Date(end.getTime() - 3600_000),
  };
  Object.entries(values).forEach(([name, date]) => {
    const input = form.elements[name];
    if (!input) return;
    if (force || !input.dataset.manual) input.value = toLocalInputValue(date);
  });
}

function setCreateTab(tab) {
  state.createTab = tab;
  document.querySelectorAll("[data-create-tab]").forEach((btn) => btn.classList.toggle("active", btn.dataset.createTab === tab));
  $("planForm")?.classList.toggle("active", tab === "plan");
  $("ddlForm")?.classList.toggle("active", tab === "ddl");
  if (tab === "ddl") syncDdlPlanDefaults(false);
  renderCreatePreview();
}

function createForm() {
  return state.createTab === "ddl" ? $("ddlForm") : $("planForm");
}

function ddlPlanPayload(form) {
  const configs = [
    { planRole: "one_day_before", enabled: "oneDayEnabled", time: "oneDayTime", duration: "oneDayDuration", sortOrder: 0 },
    { planRole: "one_hour_before", enabled: "oneHourEnabled", time: "oneHourTime", duration: "oneHourDuration", sortOrder: 1 },
  ];
  return configs
    .filter((config) => form.elements[config.enabled]?.checked)
    .map((config) => ({
      planRole: config.planRole,
      stTime: toIsoFromLocal(formVal(form, config.time)),
      durationMin: Number(formVal(form, config.duration) || 30),
      sortOrder: config.sortOrder,
    }));
}

function createPayload() {
  const form = createForm();
  if (state.createTab === "ddl") {
    return {
      title: formVal(form, "title"),
      desc: formVal(form, "desc") || null,
      endTime: toIsoFromLocal(formVal(form, "endTime")),
      hardDdl: form.elements.hardDdl.checked,
      prio: formVal(form, "prio") || "high",
      plans: ddlPlanPayload(form),
    };
  }
  return {
    title: formVal(form, "title"),
    desc: formVal(form, "desc") || null,
    stTime: toIsoFromLocal(formVal(form, "stTime")),
    durationMin: Number(formVal(form, "durationMin") || 30),
    prio: formVal(form, "prio") || "mid",
  };
}

function createDisplayTime() {
  const form = createForm();
  return state.createTab === "ddl" ? (formVal(form, "endTime") || "未设置") : (formVal(form, "stTime") || "未设置");
}

function renderCreatePreview() {
  const body = $("createPreview");
  if (!body) return;
  const p = createPayload();
  const title = p.title || "等待填写标题";
  const submitBtn = $("createSubmitBtn");
  if (submitBtn) submitBtn.textContent = state.createTab === "ddl" ? "创建截止事项及计划" : "创建计划事项";
  const linkedPlans = state.createTab === "ddl"
    ? `<div class="preview-children"><div class="preview-children-title">同时创建的计划</div>${p.plans.length ? p.plans.map((plan) => `<div class="preview-child"><div><strong>${esc(ddlPlanLabels[plan.planRole] || "关联计划")}</strong><span>${esc(displayLocal(plan.stTime))}</span></div><span class="tag green">${esc(plan.durationMin)} 分钟</span></div>`).join("") : '<div class="empty compact-empty">未启用关联计划</div>'}</div>`
    : "";
  body.innerHTML = `<div class="preview-card ${p.title ? "" : "empty-preview"}"><div class="preview-title">${esc(title)}</div><div class="tags"><span class="tag ${state.createTab === "ddl" ? "purple" : "blue"}">${state.createTab === "ddl" ? "DDL" : "计划"}</span><span class="tag ${tagClass(p.prio)}">${esc(prioLabels[p.prio] || p.prio)}</span><span class="tag blue">${esc(displayLocal(createDisplayTime()))}</span>${state.createTab === "plan" ? `<span class="tag green">${esc(p.durationMin || 30)} 分钟</span>` : ""}</div>${p.desc ? `<p class="preview-desc">${esc(p.desc)}</p>` : ""}${linkedPlans}</div>`;
}

function clearCreateForms() {
  $("planForm")?.reset();
  $("ddlForm")?.reset();
  ["oneDayTime", "oneHourTime"].forEach((name) => {
    const input = $("ddlForm")?.elements[name];
    if (input) delete input.dataset.manual;
  });
  if ($("naturalText")) $("naturalText").value = "";
  renderCreatePreview();
}

function applyParsed(parsed) {
  const p = normalizeParsed(parsed);
  setCreateTab(p.tab);
  const form = createForm();
  form.elements.title.value = p.title || "";
  form.elements.desc.value = p.desc || "";
  form.elements.prio.value = normalizePrio(p.prio, p.tab);
  if (p.tab === "ddl") {
    form.elements.endTime.value = p.endTime || "";
    form.elements.hardDdl.checked = Boolean(p.hardDdl);
    syncDdlPlanDefaults(true);
  } else {
    form.elements.stTime.value = p.stTime || "";
    form.elements.durationMin.value = p.durationMin || 30;
  }
  renderCreatePreview();
}

async function parseNatural() {
  const text = $("naturalText")?.value.trim();
  if (!text) return toast("请先输入内容");
  try {
    toast("正在解析...");
    setApiStatus("busy", "模型解析中");
    const resp = await apiSend("/api/llm/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, scene: "create_event" }),
    });
    if (!resp?.parsed) throw new Error("没有返回可用解析结果");
    applyParsed(resp.parsed);
    setApiStatus("ok", "模型解析完成");
    toast("已解析到表单");
  } catch (err) {
    setApiStatus("err", "模型解析失败");
    toast(err.message || "解析失败");
  }
}

async function submitCreate(ev) {
  ev.preventDefault();
  const form = createForm();
  const body = createPayload();
  if (!body.title) return toast("请填写标题");
  if (state.createTab === "ddl" && !body.endTime) return toast("请设置截止时间");
  if (state.createTab === "plan" && !body.stTime) return toast("请设置开始时间");
  if (state.createTab === "ddl" && body.plans.some((plan) => !plan.stTime)) return toast("请设置已启用关联计划的开始时间");
  try {
    await apiSend(form.dataset.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    clearCreateForms();
    toast("创建成功，已清空表单");
  } catch (err) {
    toast(err.message);
  }
}

function applyTemplate(name) {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(23, 59, 0, 0);
  if (name === "homework" || name === "exam") {
    setCreateTab("ddl");
    const f = $("ddlForm");
    f.elements.title.value = name === "homework" ? "作业 DDL" : "考试复习";
    f.elements.desc.value = name === "homework" ? "课程作业截止" : "复习重点章节并完成例题";
    f.elements.endTime.value = toLocalInputValue(d);
    f.elements.prio.value = "high";
    f.elements.hardDdl.checked = name === "homework";
    syncDdlPlanDefaults(true);
  } else {
    setCreateTab("plan");
    const f = $("planForm");
    f.elements.title.value = name === "project" ? "项目跟进" : "计划事项";
    f.elements.desc.value = name === "project" ? "检查阶段任务进展" : "";
    f.elements.stTime.value = toLocalInputValue(d);
    f.elements.durationMin.value = 30;
    f.elements.prio.value = "mid";
  }
  renderCreatePreview();
}

function initAdd() {
  ensureDdlPlanEditor();
  const ddlForm = $("ddlForm");
  ["oneDayTime", "oneHourTime"].forEach((name) => {
    ddlForm?.elements[name]?.addEventListener("input", (ev) => {
      ev.currentTarget.dataset.manual = "true";
    });
  });
  ddlForm?.elements.endTime?.addEventListener("input", () => syncDdlPlanDefaults(false));
  document.querySelectorAll("[data-create-tab]").forEach((button) => button.addEventListener("click", () => setCreateTab(button.dataset.createTab)));
  document.querySelectorAll("#planForm,#ddlForm").forEach((form) => {
    form.addEventListener("input", renderCreatePreview);
    form.addEventListener("change", renderCreatePreview);
    form.addEventListener("submit", submitCreate);
  });
  document.querySelectorAll(".template").forEach((button) => button.addEventListener("click", () => applyTemplate(button.dataset.template)));
  $("parseNaturalBtn")?.addEventListener("click", parseNatural);
  $("createSubmitBtn")?.addEventListener("click", submitCreate);
  renderCreatePreview();
}

function ideaStatus(idea) {
  return idea?.handled ? "handled" : "open";
}

function ideaRow(idea) {
  const status = ideaStatus(idea);
  const selected = state.selectedIdeaId === idea.ideaId;
  return `<article class="task-row clickable idea-card ${selected ? "selected" : ""}" data-action="selectIdea" data-id="${esc(idea.ideaId)}" data-idea-id="${esc(idea.ideaId)}" tabindex="0" role="button"><div><div class="task-title">${esc(idea.content || "未命名灵感")}</div><div class="tags"><span class="tag ${status === "handled" ? "green" : "blue"}">${status}</span><span class="tag blue">${esc(idea.createdAt || "")}</span></div></div></article>`;
}

function renderIdeas() {
  const filter = $("ideaFilter")?.value || "open";
  const q = $("globalSearch")?.value.trim().toLowerCase() || "";
  const rows = state.ideas.filter((idea) => (filter === "all" || (filter === "open" ? !idea.handled : idea.handled)) && (!q || String(idea.content || "").toLowerCase().includes(q)));
  $("ideaList").innerHTML = rows.length ? rows.slice().reverse().map(ideaRow).join("") : rowEmpty("暂无灵感");
}

function fillIdeaForm(idea = null) {
  const form = $("ideaEditForm");
  if (!form) return;
  state.selectedIdeaId = idea?.ideaId || null;
  form.reset();
  form.elements.ideaId.value = idea?.ideaId || "";
  form.elements.content.value = idea?.content || "";
  form.elements.handled.value = idea?.handled ? "handled" : "open";
  const title = $("ideaEditorTitle");
  if (title) title.textContent = idea ? "编辑灵感" : "新建灵感";
  const saveBtn = $("saveIdeaFormBtn");
  if (saveBtn) saveBtn.textContent = idea ? "保存修改" : "保存新灵感";
  $("deleteIdeaBtn")?.toggleAttribute("disabled", !idea);
  renderIdeas();
}

async function initInspire() {
  try {
    state.ideas = await apiGet("/api/idea");
    const selected = state.ideas.find((idea) => idea.ideaId === state.selectedIdeaId) || null;
    renderIdeas();
    if (selected) fillIdeaForm(selected);
    touchRefresh();
  } catch (err) {
    toast(err.message);
    setApiStatus("err", "API 异常");
  }
}

async function saveIdeaForm(ev) {
  ev.preventDefault();
  const form = ev.currentTarget;
  const ideaId = formVal(form, "ideaId");
  const content = formVal(form, "content");
  const handled = formVal(form, "handled") === "handled";
  if (!content) return toast("灵感内容不能为空");
  try {
    let saved;
    if (ideaId) {
      saved = await apiSend(`/api/idea/${ideaId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, handled }),
      });
    } else {
      saved = await apiSend("/api/idea", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, srcType: "text" }),
      });
      if (handled && saved?.ideaId) {
        saved = await apiSend(`/api/idea/${saved.ideaId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ handled: true }),
        });
      }
    }
    state.selectedIdeaId = saved?.ideaId || ideaId || null;
    await initInspire();
    toast(ideaId ? "灵感已更新" : "灵感已保存");
  } catch (err) {
    toast(err.message);
  }
}

async function deleteSelectedIdea() {
  const ideaId = formVal($("ideaEditForm"), "ideaId");
  if (!ideaId) return toast("请选择灵感");
  try {
    await apiSend(`/api/idea/${ideaId}`, { method: "DELETE" });
    state.selectedIdeaId = null;
    fillIdeaForm(null);
    await initInspire();
    toast("灵感已删除");
  } catch (err) {
    toast(err.message);
  }
}

function renderCourse() {
  $("courseTplList").innerHTML = state.courses.length
    ? state.courses.map((course) => `<div class="row-card"><div class="row-title">${esc(course.courseName || course.title)}</div><div class="row-meta">周${esc(course.weekDay)} · ${esc(course.stTime || "—")} - ${esc(course.endTime || "—")} · ${esc(course.location || "")}</div><div class="row-actions"><button class="btn" data-action="editCourse" data-id="${esc(course.evtId)}">编辑</button></div></div>`).join("")
    : rowEmpty("暂无课程");
}

function fillCourse(course = null) {
  const form = $("courseTplForm");
  form.reset();
  form.elements.evtId.value = course?.evtId || "";
  for (const key of ["courseName", "teacher", "location", "stDate", "endDate", "weekDay", "stTime", "endTime", "startWeek", "endWeek", "weekMode"]) {
    if (course?.[key] != null) form.elements[key].value = course[key];
  }
}

async function saveCourse(ev) {
  ev.preventDefault();
  const form = ev.currentTarget;
  const body = {
    courseName: formVal(form, "courseName"),
    title: formVal(form, "courseName"),
    teacher: formVal(form, "teacher") || null,
    location: formVal(form, "location") || null,
    stDate: formVal(form, "stDate"),
    endDate: formVal(form, "endDate"),
    weekDay: Number(formVal(form, "weekDay")),
    stTime: formVal(form, "stTime"),
    endTime: formVal(form, "endTime"),
    startWeek: numOrNull(formVal(form, "startWeek")),
    endWeek: numOrNull(formVal(form, "endWeek")),
    weekMode: formVal(form, "weekMode") || "all",
  };
  const id = formVal(form, "evtId");
  try {
    await apiSend(id ? `/api/evt/${id}` : "/api/courseEvt", {
      method: id ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    await initCourse(false);
    toast("已保存课程");
  } catch (err) {
    toast(err.message);
  }
}

async function initCourse(showLoading = true) {
  try {
    if (showLoading) setApiStatus("busy", "API 请求中");
    state.courses = await apiGet("/api/courseEvt");
    renderCourse();
    touchRefresh();
  } catch (err) {
    toast(err.message);
    setApiStatus("err", "API 异常");
  }
}

function logSearchText(row) {
  return Object.entries(row || {}).map(([key, value]) => `${key}:${typeof value === "object" ? JSON.stringify(value) : value ?? ""}`).join(" ").toLowerCase();
}

function logTitle(row) {
  if (state.logTab === "act") return `${row.action || "操作"} · ${row.targetKind || "target"}`;
  if (state.logTab === "notify") return `${row.title || "提醒"} · ${row.channel || "channel"}`;
  return `${row.intent || row.channel || "消息"}`;
}

function logMeta(row) {
  return [row.createdAt || row.scheduledAt || row.sentAt || "", row.result || row.stat || row.direction || "", row.targetId || row.evtId || row.externalId || row.msgId || row.notifyId || row.actId || ""].filter(Boolean).join(" · ");
}

function renderLogs() {
  const q = $("logKeyword")?.value.trim().toLowerCase() || "";
  const stat = $("logStatusFilter")?.value || "";
  const rows = (state.logs[state.logTab] || []).slice().reverse().filter((row) => (!q || logSearchText(row).includes(q)) && (!stat || row.stat === stat || row.result === stat));
  $("logList").innerHTML = rows.length
    ? rows.slice(0, 120).map((row) => `<details class="log-row"><summary><span class="row-title">${esc(logTitle(row))}</span><span class="row-meta">${esc(logMeta(row))}</span></summary><pre class="log-json">${esc(JSON.stringify(row, null, 2))}</pre></details>`).join("")
    : rowEmpty("暂无日志");
}

async function initLog() {
  try {
    const [act, notify, msg] = await Promise.all([
      apiGet("/api/log/act"),
      apiGet("/api/log/notify"),
      apiGet("/api/log/msg"),
    ]);
    state.logs = { act, notify, msg };
    renderLogs();
    touchRefresh();
  } catch (err) {
    toast(err.message);
    setApiStatus("err", "API 异常");
  }
}

function initSettings() {
  const form = $("userSettingsForm");
  if (!form) return;
  form.addEventListener("input", updateSettingsPreview);
  form.addEventListener("change", updateSettingsPreview);
  form.addEventListener("submit", saveSettings);
  updateSettingsPreview();
}

function bindCommon() {
  document.body.addEventListener("click", async (ev) => {
    const button = ev.target.closest("[data-action]");
    if (!button) return;
    if (button.dataset.action === "selectIdea") {
      const idea = state.ideas.find((item) => item.ideaId === button.dataset.id);
      if (idea) fillIdeaForm(idea);
    }
    if (button.dataset.action === "editCourse") {
      const course = state.courses.find((item) => item.evtId === button.dataset.id);
      fillCourse(course);
    }
  });
  document.body.addEventListener("keydown", (ev) => {
    const row = ev.target.closest?.("[data-action='selectIdea']");
    if (row && (ev.key === "Enter" || ev.key === " ")) {
      ev.preventDefault();
      row.click();
    }
  });
}

function bindPage() {
  if (page === "add") initAdd();
  if (page === "settings") initSettings();
  if (page === "inspire") {
    $("ideaEditForm")?.addEventListener("submit", saveIdeaForm);
    $("ideaFilter")?.addEventListener("change", () => {
      state.selectedIdeaId = null;
      fillIdeaForm(null);
      renderIdeas();
    });
    $("newIdeaBtn")?.addEventListener("click", () => fillIdeaForm(null));
    $("deleteIdeaBtn")?.addEventListener("click", deleteSelectedIdea);
    $("globalSearch")?.addEventListener("input", renderIdeas);
    fillIdeaForm(null);
  }
  if (page === "course") {
    $("courseTplForm")?.addEventListener("submit", saveCourse);
    $("newCourseBtn")?.addEventListener("click", () => fillCourse(null));
    $("deleteCourseTplBtn")?.addEventListener("click", async () => {
      const id = formVal($("courseTplForm"), "evtId");
      if (!id) return toast("请选择课程");
      try {
        await apiSend(`/api/evt/${id}`, { method: "DELETE" });
        fillCourse(null);
        await initCourse(false);
        toast("已删除");
      } catch (err) {
        toast(err.message);
      }
    });
  }
  if (page === "log") {
    document.querySelectorAll("[data-log-tab]").forEach((button) => button.addEventListener("click", () => {
      state.logTab = button.dataset.logTab;
      document.querySelectorAll("[data-log-tab]").forEach((item) => item.classList.toggle("active", item === button));
      renderLogs();
    }));
    $("logKeyword")?.addEventListener("input", renderLogs);
    $("logStatusFilter")?.addEventListener("change", renderLogs);
  }
}

async function initPage() {
  if (page === "inspire") return initInspire();
  if (page === "course") return initCourse();
  if (page === "log") return initLog();
}

ensureDeviceNav(false);
bindCommon();
bindPage();
loadCurrentUser();
initPage();
