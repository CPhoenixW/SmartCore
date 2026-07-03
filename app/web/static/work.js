const apiStatusEl = document.getElementById("apiStatus");
const lastRefreshEl = document.getElementById("lastRefresh");
const flashEl = document.getElementById("flash");
const evtSearchEl = document.getElementById("evtSearch");

let evtCache = [];

function setApiStatus(state, label) {
  if (!apiStatusEl) return;
  apiStatusEl.className = `status-pill ${state}`;
  apiStatusEl.textContent = label;
}

async function api(path, opts) {
  setApiStatus("busy", "API …");
  try {
    const resp = await fetch(path, opts);
    const data = await resp.json();
    if (!resp.ok) {
      setApiStatus("err", `API ${resp.status}`);
      return { ok: false, ...data };
    }
    setApiStatus("ok", "API 在线");
    return data;
  } catch {
    setApiStatus("err", "API 离线");
    return { ok: false };
  }
}

function showFlash(msg) {
  flashEl.textContent = msg;
  flashEl.classList.add("show");
  setTimeout(() => flashEl.classList.remove("show"), 2200);
}

function fmtDtLocal(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
}

function toIsoFromLocal(val) {
  if (!val) return null;
  const d = new Date(val);
  if (Number.isNaN(d.getTime())) return null;
  const pad = (n) => String(n).padStart(2, "0");
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const abs = Math.abs(off);
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}` +
    `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`
  );
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function prioTag(prio) {
  return `<span class="tag prio-${prio}">${prio}</span>`;
}

function renderEvtCard(evt) {
  const extra =
    evt.evtType === "life"
      ? `due ${fmtDtLocal(evt.dueAt)}`
      : evt.evtType === "ddl"
        ? `ddl ${fmtDtLocal(evt.ddlAt)}${evt.hardDdl ? " · hard" : ""}`
        : `course ${evt.classDate || "—"}`;

  const prioSel = `<select data-evt-id="${evt.evtId}" data-action="setPrio" aria-label="优先级">
      <option value="high"${evt.prio === "high" ? " selected" : ""}>high</option>
      <option value="mid"${evt.prio === "mid" ? " selected" : ""}>mid</option>
      <option value="low"${evt.prio === "low" ? " selected" : ""}>low</option>
    </select>`;

  let actions = "";
  if (evt.stat === "todo") {
    actions = `<button type="button" class="btn btn-sm btn-success" data-action="completeEvt" data-evt-id="${evt.evtId}">完成</button>
        <button type="button" class="btn btn-sm btn-danger" data-action="cancelEvt" data-evt-id="${evt.evtId}">取消</button>`;
  }

  return `<div class="evt-card" data-evt-id="${evt.evtId}" data-search="${escapeHtml(
    `${evt.title} ${evt.evtType} ${evt.prio} ${extra}`.toLowerCase(),
  )}">
      <div class="title-row">
        <span class="title" data-action="editTitle" data-evt-id="${evt.evtId}" title="点击编辑标题">${escapeHtml(evt.title)}</span>
        <button type="button" class="btn btn-sm" data-action="editTitle" data-evt-id="${evt.evtId}" aria-label="编辑标题">✎</button>
      </div>
      <div class="meta-line">
        <span class="tag">${evt.evtType}</span>${prioTag(evt.prio)} ${extra}
      </div>
      <div class="evt-actions">${prioSel}${actions}</div>
    </div>`;
}

function applyEvtSearch() {
  const q = (evtSearchEl?.value || "").trim().toLowerCase();
  document.querySelectorAll(".evt-card").forEach((card) => {
    const hay = card.dataset.search || "";
    card.classList.toggle("hidden-by-search", q.length > 0 && !hay.includes(q));
  });
}

function renderEvtBoard(evts) {
  evtCache = evts;
  const groups = { todo: [], done: [], cancelled: [] };
  evts.forEach((e) => {
    if (groups[e.stat]) groups[e.stat].push(e);
  });

  ["todo", "done", "cancelled"].forEach((stat) => {
    const listEl = document.getElementById(
      "evtList" + stat.charAt(0).toUpperCase() + stat.slice(1),
    );
    const countEl = document.getElementById(stat + "Count");
    const items = groups[stat];
    countEl.textContent = items.length;
    listEl.innerHTML = items.length
      ? items.map(renderEvtCard).join("")
      : '<span class="empty">无</span>';
  });
  applyEvtSearch();
  touchRefresh();
}

async function loadEvts() {
  const resp = await api("/api/evt");
  renderEvtBoard(resp.data || []);
}

async function loadIdeas() {
  const resp = await api("/api/idea");
  const ideas = resp.data || [];
  const el = document.getElementById("ideaList");
  el.innerHTML = ideas.length
    ? ideas
        .map(
          (i) => `<div class="log-item">
          <div class="log-title">${escapeHtml(i.content)}</div>
          <div class="log-meta">${i.handled ? "handled" : "open"} · ${fmtDtLocal(i.createdAt)}</div>
        </div>`,
        )
        .join("")
    : '<span class="empty">无</span>';
}

async function loadDevState() {
  const resp = await api("/api/devState");
  const rows = resp.data || [];
  const el = document.getElementById("devStateBody");
  if (!rows.length) {
    el.innerHTML = '<span class="empty">暂无设备上报</span>';
    return;
  }
  const latest = rows[0];
  const cls = ["working", "away", "offline"].includes(latest.state) ? latest.state : "";
  const meta = latest.meta && typeof latest.meta === "object" ? latest.meta : {};
  const identity = meta.identity ? `<br>identity: ${escapeHtml(meta.identity)}` : "";
  const detail = meta.detail ? `<br>detail: ${escapeHtml(meta.detail)}` : "";
  el.innerHTML = `<div class="dev-card">
      <div><span class="dev-badge ${cls}">${escapeHtml(latest.state)}</span></div>
      <div class="log-meta">
        devId: ${escapeHtml(latest.devId)}<br>
        confidence: ${latest.confidence ?? "—"}<br>
        seenAt: ${fmtDtLocal(latest.seenAt)}${identity}${detail}
      </div>
    </div>`;
}

function renderLogList(elId, rows, renderFn) {
  const el = document.getElementById(elId);
  el.innerHTML = rows.length
    ? rows
        .slice()
        .reverse()
        .slice(0, 40)
        .map(renderFn)
        .join("")
    : '<span class="empty">无</span>';
}

async function loadNotifyLog() {
  const resp = await api("/api/notifyLog");
  renderLogList("notifyLogList", resp.data || [], (r) =>
    `<div class="log-item"><div class="log-title">${escapeHtml(r.title)}</div>
       <div class="log-meta">${r.stat} · ${escapeHtml(r.targetKind || "")} · ${fmtDtLocal(r.scheduledAt)}</div></div>`,
  );
}

async function loadMsgLog() {
  const resp = await api("/api/msgLog");
  renderLogList("msgLogList", resp.data || [], (r) =>
    `<div class="log-item"><div class="log-title">${escapeHtml(r.rawText || "—")}</div>
       <div class="log-meta">${r.src} · ${r.stat || "—"} · ${fmtDtLocal(r.createdAt)}</div></div>`,
  );
}

async function loadActLog() {
  const resp = await api("/api/actLog");
  renderLogList("actLogList", resp.data || [], (r) =>
    `<div class="log-item"><div class="log-title">${escapeHtml(r.actType)} → ${escapeHtml(r.targetKind || "")}</div>
       <div class="log-meta">${r.src} · ${fmtDtLocal(r.createdAt)}</div></div>`,
  );
}

function touchRefresh() {
  lastRefreshEl.textContent = "更新于 " + new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

async function refreshAll() {
  await Promise.all([
    loadEvts(),
    loadIdeas(),
    loadDevState(),
    loadNotifyLog(),
    loadMsgLog(),
    loadActLog(),
  ]);
}

async function patchEvt(evtId, body) {
  const resp = await api(`/api/evt/${evtId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error("patch failed");
  return resp.data;
}

async function completeEvt(evtId) {
  await patchEvt(evtId, { stat: "done" });
  showFlash("已标记完成");
  await loadEvts();
  await loadActLog();
}

async function cancelEvt(evtId) {
  await api(`/api/evt/${evtId}`, { method: "DELETE" });
  showFlash("已取消");
  await loadEvts();
  await loadActLog();
}

async function setPrio(evtId, prio) {
  await patchEvt(evtId, { prio });
  showFlash("优先级已更新");
  await loadEvts();
}

async function editTitle(evtId) {
  const evt = evtCache.find((e) => e.evtId === evtId);
  if (!evt) return;
  const card = document.querySelector(`.evt-card[data-evt-id="${evtId}"] .title-row`);
  if (!card || card.querySelector(".title-input")) return;

  const input = document.createElement("input");
  input.type = "text";
  input.className = "title-input";
  input.value = evt.title;
  input.setAttribute("aria-label", "编辑标题");

  const save = async () => {
    const title = input.value.trim();
    if (!title || title === evt.title) {
      await loadEvts();
      return;
    }
    await patchEvt(evtId, { title });
    showFlash("标题已更新");
    await loadEvts();
    await loadActLog();
  };

  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      save();
    } else if (ev.key === "Escape") {
      loadEvts();
    }
  });
  input.addEventListener("blur", () => save());

  card.innerHTML = "";
  card.appendChild(input);
  input.focus();
  input.select();
}

function bindQuickForm(formId, buildBody) {
  const form = document.getElementById(formId);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const endpoint = form.dataset.endpoint;
    const body = buildBody(form);
    const resp = await api(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (resp.ok) {
      form.reset();
      showFlash("创建成功");
      await refreshAll();
    }
  });

  form.addEventListener("keydown", (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") {
      ev.preventDefault();
      form.requestSubmit();
    }
  });
}

function bindLogTabs() {
  const tabs = document.querySelectorAll(".log-tab");
  const panes = document.querySelectorAll(".log-pane");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const name = tab.dataset.logTab;
      tabs.forEach((t) => t.classList.toggle("active", t === tab));
      panes.forEach((p) => p.classList.toggle("active", p.dataset.logPane === name));
    });
  });
}

bindQuickForm("lifeEvtForm", (form) => ({
  title: form.title.value.trim(),
  dueAt: toIsoFromLocal(form.dueAt.value),
  prio: form.prio.value,
}));

bindQuickForm("ddlEvtForm", (form) => ({
  title: form.title.value.trim(),
  ddlAt: toIsoFromLocal(form.ddlAt.value),
  hardDdl: form.hardDdl.checked,
  prio: form.prio.value,
}));

bindQuickForm("ideaForm", (form) => ({
  content: form.content.value.trim(),
  srcType: "text",
}));

document.body.addEventListener("click", async (ev) => {
  const btn = ev.target.closest("[data-action]");
  if (!btn) return;
  const action = btn.dataset.action;
  if (action === "refreshEvt") await loadEvts();
  else if (action === "refreshIdea") await loadIdeas();
  else if (action === "refreshDev") await loadDevState();
  else if (action === "refreshNotify") await loadNotifyLog();
  else if (action === "refreshMsg") await loadMsgLog();
  else if (action === "refreshAct") await loadActLog();
  else if (action === "refreshAll") await refreshAll();
  else if (action === "completeEvt") await completeEvt(btn.dataset.evtId);
  else if (action === "cancelEvt") await cancelEvt(btn.dataset.evtId);
  else if (action === "editTitle") await editTitle(btn.dataset.evtId);
});

document.body.addEventListener("change", async (ev) => {
  const sel = ev.target.closest('[data-action="setPrio"]');
  if (!sel) return;
  await setPrio(sel.dataset.evtId, sel.value);
});

if (evtSearchEl) {
  evtSearchEl.addEventListener("input", applyEvtSearch);
}

bindLogTabs();
refreshAll();
