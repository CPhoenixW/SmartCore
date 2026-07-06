# ruff: noqa: E501
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["work"])

_WORK_ADD_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SmartCore 添加事件</title>
<style>
:root {
  --bg: #f5f7fb;
  --surface: #ffffff;
  --surface2: #f8fafc;
  --border: #e2e8f0;
  --border-strong: #cbd5e1;
  --text: #111827;
  --muted: #64748b;
  --accent: #2563eb;
  --accent-soft: #eaf2ff;
  --success: #16a34a;
  --warn: #f59e0b;
  --danger: #ef4444;
  --purple: #7c3aed;
  --shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
  line-height: 1.45;
}
a { color: inherit; text-decoration: none; }
button, input, textarea, select { font: inherit; }
.layout { display: grid; grid-template-columns: 236px minmax(0, 1fr); min-height: 100vh; }
.sidebar {
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: 22px 18px;
  position: sticky;
  top: 0;
  height: 100vh;
}
.brand { display: flex; align-items: center; gap: 10px; margin-bottom: 34px; }
.brand-mark {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--accent);
  color: #fff;
  display: grid;
  place-items: center;
  font-weight: 800;
  font-size: 13px;
  box-shadow: 0 8px 16px rgba(37, 99, 235, 0.22);
}
.brand-title { font-weight: 750; font-size: 18px; letter-spacing: -0.02em; }
.brand-sub { color: var(--muted); font-size: 12px; margin-top: 1px; }
.nav { display: grid; gap: 8px; }
.nav-link {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 42px;
  padding: 0 12px;
  border-radius: 12px;
  color: #475569;
  font-size: 14px;
  font-weight: 620;
}
.nav-link:hover { background: var(--surface2); color: var(--text); }
.nav-link.active { background: var(--accent-soft); color: var(--accent); }
.nav-ico { width: 20px; text-align: center; color: currentColor; }
.sidebar-foot { position: absolute; left: 18px; right: 18px; bottom: 22px; }
.main { min-width: 0; }
.topbar {
  height: 76px;
  background: rgba(255, 255, 255, 0.92);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 28px;
  position: sticky;
  top: 0;
  z-index: 10;
  backdrop-filter: blur(12px);
}
.search {
  width: min(520px, 48vw);
  height: 40px;
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  background: var(--surface);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  color: var(--muted);
}
.search input { border: none; outline: none; background: transparent; flex: 1; min-width: 0; }
.top-meta { display: flex; align-items: center; gap: 12px; color: var(--muted); font-size: 14px; }
.pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 34px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  font-weight: 700;
  color: var(--muted);
}
.pill::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.pill.warn { color: #b45309; background: #fffbeb; border-color: #fde68a; }
.pill.ok { color: #15803d; background: #f0fdf4; border-color: #bbf7d0; }
.pill.err { color: #dc2626; background: #fef2f2; border-color: #fecaca; }
.content { max-width: 1360px; margin: 0 auto; padding: 28px; }
.page-head { margin-bottom: 22px; }
.page-head h1 { margin: 0; font-size: 30px; line-height: 1.2; letter-spacing: -0.03em; }
.page-head p { margin: 8px 0 0; color: var(--muted); font-size: 15px; }
.grid {
  display: grid;
  grid-template-columns: minmax(560px, 1.25fr) minmax(360px, 0.75fr);
  gap: 20px;
  align-items: start;
}
.stack { display: grid; gap: 18px; }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 18px;
  box-shadow: var(--shadow);
  overflow: hidden;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px 0;
}
.card-head h2 { margin: 0; font-size: 18px; letter-spacing: -0.01em; }
.card-body { padding: 18px 20px 20px; }
.help { margin: 6px 0 0; color: var(--muted); font-size: 13px; }
.nl-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  margin-top: 14px;
}
.nl-input {
  min-height: 46px;
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  padding: 12px 14px;
  outline: none;
  resize: vertical;
  background: var(--surface);
}
.nl-input:focus, input:focus, textarea:focus, select:focus {
  border-color: #93c5fd;
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.11);
  outline: none;
}
.btn {
  border: 1px solid var(--border-strong);
  background: var(--surface);
  color: var(--text);
  min-height: 40px;
  border-radius: 11px;
  padding: 0 14px;
  font-weight: 700;
  cursor: pointer;
}
.btn:hover { background: var(--surface2); }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-primary:hover { background: #1d4ed8; }
.btn-block { width: 100%; }
.tabs { display: flex; gap: 8px; padding: 0 20px; border-bottom: 1px solid var(--border); }
.tab {
  appearance: none;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  padding: 14px 8px 12px;
  color: var(--muted);
  font-weight: 750;
  cursor: pointer;
}
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.form-pane { display: none; }
.form-pane.active { display: block; }
.form-grid { display: grid; gap: 14px; }
.form-grid.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.field { display: grid; gap: 7px; color: var(--muted); font-size: 13px; font-weight: 650; }
.field.required > span::after { content: " *"; color: var(--danger); }
.field input, .field textarea, .field select {
  width: 100%;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 12px;
  min-height: 42px;
  padding: 10px 12px;
  color: var(--text);
}
.field textarea { resize: vertical; min-height: 86px; }
.check-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface2);
  color: var(--text);
  font-size: 14px;
  font-weight: 650;
}
.check-row input { margin-top: 3px; }
.check-row small { display: block; margin-top: 2px; color: var(--muted); font-weight: 400; }
.form-actions { padding-top: 4px; }
.preview-card {
  border: 1px solid var(--border);
  border-radius: 16px;
  background: linear-gradient(180deg, #fff 0%, #fbfdff 100%);
  padding: 18px;
}
.preview-kicker { color: var(--muted); font-size: 12px; font-weight: 750; text-transform: uppercase; letter-spacing: 0.06em; }
.preview-title { margin: 10px 0 10px; font-size: 22px; font-weight: 800; letter-spacing: -0.02em; }
.preview-desc { margin: 12px 0 0; color: #475569; font-size: 14px; }
.tags { display: flex; flex-wrap: wrap; gap: 7px; }
.tag { padding: 4px 9px; border-radius: 8px; font-size: 12px; font-weight: 750; border: 1px solid var(--border); background: var(--surface2); color: var(--muted); }
.tag.blue { color: var(--accent); background: var(--accent-soft); border-color: #bfdbfe; }
.tag.red { color: #dc2626; background: #fef2f2; border-color: #fecaca; }
.tag.orange { color: #b45309; background: #fffbeb; border-color: #fde68a; }
.tag.purple { color: var(--purple); background: #f5f3ff; border-color: #ddd6fe; }
.meta-list { margin-top: 16px; display: grid; gap: 10px; }
.meta-row { display: flex; justify-content: space-between; gap: 12px; color: var(--muted); font-size: 14px; }
.meta-row strong { color: var(--text); font-weight: 700; text-align: right; }
.templates { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.template {
  text-align: left;
  min-height: 70px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface);
  cursor: pointer;
}
.template:hover { border-color: #93c5fd; background: #fbfdff; }
.template strong { display: block; margin-bottom: 3px; }
.template span { color: var(--muted); font-size: 12px; }
.notice { padding: 12px 14px; border-radius: 12px; background: #f8fafc; border: 1px solid var(--border); color: var(--muted); font-size: 13px; }
.toast {
  position: fixed;
  right: 24px;
  bottom: 24px;
  min-width: 220px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--surface);
  box-shadow: var(--shadow);
  opacity: 0;
  transform: translateY(8px);
  pointer-events: none;
  transition: 0.18s ease;
  color: var(--text);
  font-weight: 650;
}
.toast.show { opacity: 1; transform: translateY(0); }
@media (max-width: 1080px) {
  .layout { grid-template-columns: 1fr; }
  .sidebar { position: static; height: auto; width: auto; }
  .nav { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .sidebar-foot { position: static; margin-top: 20px; }
  .grid { grid-template-columns: 1fr; }
  .topbar { position: static; }
}
@media (max-width: 720px) {
  .content { padding: 18px; }
  .topbar { align-items: stretch; height: auto; padding: 14px 18px; flex-direction: column; }
  .search { width: 100%; }
  .top-meta { width: 100%; justify-content: space-between; flex-wrap: wrap; }
  .form-grid.two, .templates, .nl-row { grid-template-columns: 1fr; }
}
</style>
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark">SC</div>
      <div>
        <div class="brand-title">SmartCore</div>
        <div class="brand-sub">学生智能助手</div>
      </div>
    </div>
    <nav class="nav" aria-label="工作台导航">
      <a class="nav-link" href="/work#overview"><span class="nav-ico">⌂</span>总览</a>
      <a class="nav-link active" href="/work/add"><span class="nav-ico">＋</span>添加事件</a>
      <a class="nav-link" href="/work#evtBoard"><span class="nav-ico">▦</span>事项看板</a>
      <a class="nav-link" href="/work#idea"><span class="nav-ico">♢</span>灵感</a>
      <a class="nav-link" href="/work#course"><span class="nav-ico">□</span>课程</a>
      <a class="nav-link" href="/work#dev"><span class="nav-ico">▣</span>设备</a>
      <a class="nav-link" href="/work#log"><span class="nav-ico">≡</span>日志</a>
    </nav>
    <div class="sidebar-foot">
      <a class="nav-link" href="/work#settings"><span class="nav-ico">⚙</span>设置</a>
    </div>
  </aside>

  <section class="main">
    <header class="topbar">
      <label class="search">
        <span>⌕</span>
        <input id="quickSearch" placeholder="搜索事项、DDL、灵感、设备日志..." autocomplete="off">
      </label>
      <div class="top-meta">
        <span class="pill warn">Away</span>
        <span class="pill" id="apiBadge">API 待命</span>
        <span id="lastUpdate">未请求后端</span>
        <a class="btn" href="/work#evtBoard">回到看板</a>
      </div>
    </header>

    <main class="content">
      <section class="page-head">
        <h1>添加事件</h1>
        <p>独立录入页：只在提交时调用创建接口，避免进入页面时触发全量刷新和其他后端模块。</p>
      </section>

      <section class="grid">
        <div class="stack">
          <section class="card">
            <div class="card-head">
              <div>
                <h2>一句话录入</h2>
                <p class="help">本地解析并预填表单，不会直接创建。</p>
              </div>
            </div>
            <div class="card-body">
              <div class="nl-row">
                <textarea id="naturalText" class="nl-input" rows="2" placeholder="例如：明天晚上八点提醒我复习热流体，优先级高"></textarea>
                <button type="button" class="btn btn-primary" id="parseBtn">解析并预填</button>
              </div>
            </div>
          </section>

          <section class="card">
            <div class="card-head">
              <h2>事件表单</h2>
            </div>
            <div class="tabs" role="tablist">
              <button type="button" class="tab active" data-tab="life">普通事项</button>
              <button type="button" class="tab" data-tab="ddl">截止事项</button>
            </div>
            <div class="card-body">
              <form id="lifeForm" class="form-pane active" data-endpoint="/api/lifeEvt">
                <div class="form-grid">
                  <label class="field required"><span>标题</span><input name="title" required maxlength="100" placeholder="例如：洗衣服"></label>
                  <label class="field"><span>描述</span><textarea name="desc" maxlength="500" placeholder="补充说明，可为空"></textarea></label>
                  <div class="form-grid two">
                    <label class="field"><span>提醒时间 / 截止时间</span><input name="dueAt" type="datetime-local"></label>
                    <label class="field"><span>优先级</span><select name="prio"><option value="mid" selected>中优先级</option><option value="high">高优先级</option><option value="low">低优先级</option></select></label>
                  </div>
                  <div class="form-actions"><button type="submit" class="btn btn-primary btn-block">创建普通事项</button></div>
                </div>
              </form>

              <form id="ddlForm" class="form-pane" data-endpoint="/api/ddlEvt">
                <div class="form-grid">
                  <label class="field required"><span>标题</span><input name="title" required maxlength="100" placeholder="例如：复习热流体"></label>
                  <label class="field"><span>描述</span><textarea name="desc" maxlength="500" placeholder="补充说明，可为空"></textarea></label>
                  <div class="form-grid two">
                    <label class="field required"><span>截止时间</span><input name="ddlAt" type="datetime-local" required></label>
                    <label class="field"><span>优先级</span><select name="prio"><option value="mid" selected>中优先级</option><option value="high">高优先级</option><option value="low">低优先级</option></select></label>
                  </div>
                  <label class="check-row"><input name="hardDdl" type="checkbox"><span>硬性截止 <small>到期后仍未完成时保持高优先级提醒。</small></span></label>
                  <div class="form-actions"><button type="submit" class="btn btn-primary btn-block">创建截止事项</button></div>
                </div>
              </form>
            </div>
          </section>
        </div>

        <aside class="stack">
          <section class="card">
            <div class="card-head"><h2>创建前预览</h2></div>
            <div class="card-body">
              <article class="preview-card" id="previewCard"></article>
            </div>
          </section>

          <section class="card">
            <div class="card-head"><h2>常用模板</h2></div>
            <div class="card-body">
              <div class="templates">
                <button type="button" class="template" data-template="homework"><strong>作业 DDL</strong><span>课程作业截止</span></button>
                <button type="button" class="template" data-template="life"><strong>生活提醒</strong><span>日常提醒安排</span></button>
                <button type="button" class="template" data-template="exam"><strong>考试复习</strong><span>复习计划节点</span></button>
                <button type="button" class="template" data-template="project"><strong>项目跟进</strong><span>阶段检查事项</span></button>
              </div>
            </div>
          </section>

          <section class="notice">
            <strong>本页策略：</strong>页面加载不访问 `/api/evt`、`/api/courseTpl`、`/api/devState`、`/api/*Log`。只有创建普通事项或截止事项时才请求后端，便于逐页排查问题。
          </section>
        </aside>
      </section>
    </main>
  </section>
</div>
<div class="toast" id="toast"></div>
<script>
const state = { tab: "life" };
const $ = (id) => document.getElementById(id);
const prioLabels = { high: "高优先级", mid: "中优先级", low: "低优先级" };

function setApiBadge(kind, text) {
  const badge = $("apiBadge");
  badge.className = `pill ${kind || ""}`.trim();
  badge.textContent = text;
}

function showToast(text) {
  const toast = $("toast");
  toast.textContent = text;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2400);
}

function updateTime() {
  $("lastUpdate").textContent = "最后操作 " + new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function formValue(form, name) {
  return form.elements[name]?.value?.trim() || "";
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

function toLocalInputValue(date) {
  const d = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatLocalTime(value) {
  if (!value) return "未设置";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function setTab(tab) {
  state.tab = tab;
  document.querySelectorAll(".tab").forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === tab));
  document.querySelectorAll(".form-pane").forEach((pane) => pane.classList.toggle("active", pane.id === `${tab}Form`));
  renderPreview();
}

function currentForm() {
  return state.tab === "ddl" ? $("ddlForm") : $("lifeForm");
}

function currentPayload() {
  const form = currentForm();
  if (state.tab === "ddl") {
    return {
      type: "DDL",
      title: formValue(form, "title"),
      desc: formValue(form, "desc"),
      timeLabel: formatLocalTime(formValue(form, "ddlAt")),
      prio: formValue(form, "prio") || "mid",
      hardDdl: Boolean(form.elements.hardDdl.checked),
      body: {
        title: formValue(form, "title"),
        desc: formValue(form, "desc") || null,
        ddlAt: toIsoFromLocal(formValue(form, "ddlAt")),
        hardDdl: Boolean(form.elements.hardDdl.checked),
        prio: formValue(form, "prio") || "mid",
      },
    };
  }
  return {
    type: "普通事项",
    title: formValue(form, "title"),
    desc: formValue(form, "desc"),
    timeLabel: formatLocalTime(formValue(form, "dueAt")),
    prio: formValue(form, "prio") || "mid",
    hardDdl: false,
    body: {
      title: formValue(form, "title"),
      desc: formValue(form, "desc") || null,
      dueAt: toIsoFromLocal(formValue(form, "dueAt")),
      prio: formValue(form, "prio") || "mid",
    },
  };
}

function renderPreview() {
  const p = currentPayload();
  const title = p.title || "等待填写标题";
  const desc = p.desc || "填写描述后会在这里展示。";
  const hardText = p.type === "DDL" ? (p.hardDdl ? "硬性截止" : "非硬性截止") : "普通提醒";
  const typeClass = p.type === "DDL" ? "purple" : "blue";
  const prioClass = p.prio === "high" ? "red" : p.prio === "low" ? "blue" : "orange";
  $("previewCard").innerHTML = `
    <div class="preview-kicker">Create Preview</div>
    <div class="preview-title">${escapeHtml(title)}</div>
    <div class="tags">
      <span class="tag ${typeClass}">${escapeHtml(p.type)}</span>
      <span class="tag ${prioClass}">${escapeHtml(prioLabels[p.prio] || p.prio)}</span>
      <span class="tag blue">${escapeHtml(p.timeLabel)}</span>
      <span class="tag">${escapeHtml(hardText)}</span>
    </div>
    <p class="preview-desc">${escapeHtml(desc)}</p>
    <div class="meta-list">
      <div class="meta-row"><span>创建接口</span><strong>${state.tab === "ddl" ? "/api/ddlEvt" : "/api/lifeEvt"}</strong></div>
      <div class="meta-row"><span>创建来源</span><strong>手动录入 / 本地预填</strong></div>
      <div class="meta-row"><span>提交策略</span><strong>只提交当前表单</strong></div>
    </div>`;
}

async function postForm(form) {
  const payload = currentPayload();
  if (!payload.body.title) {
    showToast("请先填写标题");
    return;
  }
  if (state.tab === "ddl" && !payload.body.ddlAt) {
    showToast("请设置截止时间");
    return;
  }
  setApiBadge("", "API 请求中");
  try {
    const resp = await fetch(form.dataset.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload.body),
    });
    let data = null;
    try { data = await resp.json(); } catch { data = null; }
    if (!resp.ok || data?.ok === false) {
      setApiBadge("err", `API ${resp.status}`);
      showToast(data?.msg || data?.detail || "创建失败，请看服务端日志");
      return;
    }
    setApiBadge("ok", "API 在线");
    updateTime();
    form.reset();
    renderPreview();
    showToast("创建成功");
  } catch (err) {
    setApiBadge("err", "API 离线");
    showToast("网络错误，未创建");
  }
}

function parseChineseNumber(raw) {
  const map = { "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10 };
  if (/^\d+$/.test(raw)) return Number(raw);
  if (raw === "十") return 10;
  if (raw.startsWith("十")) return 10 + (map[raw.slice(1)] || 0);
  if (raw.endsWith("十")) return (map[raw[0]] || 1) * 10;
  if (raw.includes("十")) {
    const [a, b] = raw.split("十");
    return (map[a] || 1) * 10 + (map[b] || 0);
  }
  return map[raw] ?? null;
}

function parseNatural() {
  const text = $("naturalText").value.trim();
  if (!text) {
    showToast("请先输入一句话描述");
    return;
  }
  const isDdl = /ddl|deadline|截止|交|提交|作业|考试|复习/iu.test(text);
  setTab(isDdl ? "ddl" : "life");
  const form = currentForm();
  const cleaned = text
    .replace(/^(帮我|提醒我|创建|添加|新建|安排)\s*/u, "")
    .replace(/，?优先级[高中低]/u, "")
    .replace(/高优先级|中优先级|低优先级/u, "")
    .trim();
  form.elements.title.value = cleaned.slice(0, 80) || text.slice(0, 80);
  form.elements.desc.value = text;
  if (/高优先级|优先级高|紧急|重要/iu.test(text)) form.elements.prio.value = "high";
  else if (/低优先级|优先级低/iu.test(text)) form.elements.prio.value = "low";
  else form.elements.prio.value = "mid";

  const target = new Date();
  if (/后天/u.test(text)) target.setDate(target.getDate() + 2);
  else if (/明天/u.test(text)) target.setDate(target.getDate() + 1);

  const hourMatch = text.match(/(上午|中午|下午|晚上|今晚|早上)?\s*([零一二两三四五六七八九十\d]{1,3})\s*(点|时)(半|[零一二三四五六七八九十\d]{1,2}分?)?/u);
  if (hourMatch) {
    let hour = parseChineseNumber(hourMatch[2]);
    let minute = 0;
    if (hourMatch[4] === "半") minute = 30;
    else if (hourMatch[4]) minute = parseChineseNumber(hourMatch[4].replace("分", "")) || 0;
    const part = hourMatch[1] || "";
    if ((part.includes("下午") || part.includes("晚上") || part.includes("今晚")) && hour < 12) hour += 12;
    if (part.includes("中午") && hour < 11) hour += 12;
    target.setHours(hour, minute, 0, 0);
  } else {
    target.setHours(isDdl ? 23 : 20, 0, 0, 0);
  }

  if (state.tab === "ddl") {
    form.elements.ddlAt.value = toLocalInputValue(target);
    form.elements.hardDdl.checked = /硬性|必须|一定|截止/iu.test(text);
  } else {
    form.elements.dueAt.value = toLocalInputValue(target);
  }
  renderPreview();
  showToast("已预填，请确认后创建");
}

function applyTemplate(name) {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(23, 59, 0, 0);
  if (name === "homework") {
    setTab("ddl");
    const f = $("ddlForm");
    f.elements.title.value = "作业 DDL";
    f.elements.desc.value = "课程作业截止";
    f.elements.ddlAt.value = toLocalInputValue(d);
    f.elements.prio.value = "high";
    f.elements.hardDdl.checked = true;
  } else if (name === "exam") {
    setTab("ddl");
    const f = $("ddlForm");
    f.elements.title.value = "考试复习";
    f.elements.desc.value = "复习重点章节并完成例题";
    f.elements.ddlAt.value = toLocalInputValue(d);
    f.elements.prio.value = "high";
  } else if (name === "project") {
    setTab("life");
    const f = $("lifeForm");
    f.elements.title.value = "项目跟进";
    f.elements.desc.value = "检查阶段任务进展";
    f.elements.dueAt.value = toLocalInputValue(d);
    f.elements.prio.value = "mid";
  } else {
    setTab("life");
    const f = $("lifeForm");
    f.elements.title.value = "生活提醒";
    f.elements.desc.value = "";
    f.elements.dueAt.value = toLocalInputValue(d);
    f.elements.prio.value = "mid";
  }
  renderPreview();
  showToast("已应用模板");
}

document.querySelectorAll(".tab").forEach((btn) => btn.addEventListener("click", () => setTab(btn.dataset.tab)));
document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("input", renderPreview);
  form.addEventListener("change", renderPreview);
  form.addEventListener("submit", (ev) => { ev.preventDefault(); postForm(form); });
});
document.querySelectorAll(".template").forEach((btn) => btn.addEventListener("click", () => applyTemplate(btn.dataset.template)));
$("parseBtn").addEventListener("click", parseNatural);
setApiBadge("", "API 待命");
renderPreview();
</script>
</body>
</html>"""


@router.get("/work/add", response_class=HTMLResponse)
def workAddPage() -> str:
    return _WORK_ADD_HTML
