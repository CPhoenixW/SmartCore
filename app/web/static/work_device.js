import { deviceStateView, formatDateTime } from "./work_shared.js";

const $ = (id) => document.getElementById(id);
const state = {
  logs: [],
  photoRequests: [],
  activeRequestId: null,
  pollTimer: null,
};

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

function markRefresh() {
  if ($("lastRefresh")) $("lastRefresh").textContent = "更新于 " + new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

async function apiGet(path) {
  const response = await fetch(path);
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.ok === false) throw new Error(body.detail || body.msg || `HTTP ${response.status}`);
  return body.data;
}

async function apiSend(path, options) {
  setApi("busy", "API 请求中");
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.ok === false) {
    setApi("err", "API 异常");
    throw new Error(body.detail || body.msg || `HTTP ${response.status}`);
  }
  setApi("ok", "API 在线");
  markRefresh();
  return body.data;
}

function avatarText(name) {
  const text = String(name || "SC").trim();
  return text.slice(0, 2).toUpperCase() || "SC";
}

async function loadTopUser() {
  try {
    const user = await apiGet("/api/user/me");
    const img = $("topAvatarImg");
    const text = $("topAvatarText");
    text.textContent = avatarText(user?.displayName);
    if (user?.avatarUrl) {
      img.src = user.avatarUrl;
      img.hidden = false;
      text.hidden = true;
    }
  } catch {
    $("topAvatarText").textContent = "SC";
  }
}

function latestPiLog() {
  return state.logs.find((row) => row.deviceId === "pi") || null;
}

function personNames(view) {
  return view.persons.map((person) => person.name || person.personId).filter(Boolean);
}

function renderCurrentState() {
  const view = deviceStateView(latestPiLog());
  $("deviceStateDot").className = `device-state-dot ${view.state}`;
  $("deviceStateTitle").textContent = view.label;
  $("deviceStateSeen").textContent = view.seenAt ? `最后回传：${formatDateTime(view.seenAt)}` : "尚未收到树莓派回传";
  $("devicePresent").textContent = view.present && !view.stale ? "有人" : "无人";
  const names = personNames(view);
  $("devicePersons").textContent = names.length ? names.join("、") : "未识别";
  $("deviceConfidence").textContent = view.confidence == null ? "—" : `${Math.round(Number(view.confidence) * 100)}%`;
  const skew = Number(view.meta.clockSkewSeconds);
  $("deviceClockSkew").textContent = Number.isFinite(skew) ? `${skew >= 0 ? "+" : ""}${skew.toFixed(2)} 秒` : "—";
  $("deviceModel").textContent = view.meta.model || "—";
  $("deviceCamera").textContent = view.meta.camera || "—";
}

function logText(row) {
  const meta = row.meta && typeof row.meta === "object" ? row.meta : {};
  return `${row.state || ""} ${row.seenAt || ""} ${JSON.stringify(meta)}`.toLowerCase();
}

function renderLogs() {
  const query = $("deviceLogSearch")?.value.trim().toLowerCase() || "";
  const rows = state.logs.filter((row) => row.deviceId === "pi" && (!query || logText(row).includes(query))).slice(0, 240);
  $("deviceLogCount").textContent = `${rows.length} 条`;
  $("deviceLogList").innerHTML = rows.length
    ? rows.map((row) => {
      const view = deviceStateView(row, Number.MAX_SAFE_INTEGER);
      const names = personNames(view);
      const confidence = row.confidence == null ? "—" : `${Math.round(Number(row.confidence) * 100)}%`;
      return `<details class="log-row device-log-row"><summary><span class="row-title"><span class="device-state-dot ${esc(row.state || "unknown")}"></span>${esc(view.label)} · ${esc(names.length ? names.join("、") : "未识别人物")}</span><span class="row-meta">${esc(formatDateTime(row.seenAt))} · 置信度 ${esc(confidence)}</span></summary><pre class="log-json">${esc(JSON.stringify(row, null, 2))}</pre></details>`;
    }).join("")
    : '<div class="empty">暂无树莓派识别日志</div>';
}

function photoStatusLabel(value) {
  return {
    pending: "等待树莓派",
    uploaded: "已上传",
    failed: "失败",
    expired: "已过期",
    cancelled: "已取消",
  }[value] || value || "未知";
}

function photoStatusClass(value) {
  if (value === "uploaded") return "green";
  if (value === "failed" || value === "expired") return "red";
  return "orange";
}

function renderPhotoRequests() {
  $("photoRequestList").innerHTML = state.photoRequests.length
    ? state.photoRequests.map((item) => `<article class="row-card"><div class="row-title">${esc(item.reason || "请求当前画面")}</div><div class="tags"><span class="tag ${photoStatusClass(item.stat)}">${esc(photoStatusLabel(item.stat))}</span><span class="tag blue">${esc(formatDateTime(item.requestedAt))}</span></div>${item.errorMessage ? `<p class="task-desc">${esc(item.errorMessage)}</p>` : ""}${item.imageAvailable ? `<div class="row-actions"><button class="btn" data-view-photo="${esc(item.requestId)}" data-image-url="${esc(item.imageUrl)}">查看画面</button></div>` : ""}</article>`).join("")
    : '<div class="empty">暂无照片请求</div>';
}

function showPhoto(item) {
  if (!item?.imageAvailable || !item.imageUrl) return;
  const image = $("cameraImage");
  image.src = `${item.imageUrl}?t=${Date.now()}`;
  image.hidden = false;
  $("cameraFrame").classList.add("has-image");
  $("cameraFrame").querySelector("span")?.setAttribute("hidden", "hidden");
  $("cameraRequestMeta").textContent = `拍摄于 ${formatDateTime(item.capturedAt)} · ${item.imageSize || 0} bytes`;
}

async function refreshDevice() {
  try {
    setApi("busy", "API 请求中");
    const [logs, photos] = await Promise.all([
      apiGet("/api/devState"),
      apiGet("/api/device/pi/photoRequests?limit=50"),
    ]);
    state.logs = Array.isArray(logs) ? logs : [];
    state.photoRequests = Array.isArray(photos) ? photos : [];
    renderCurrentState();
    renderLogs();
    renderPhotoRequests();
    setApi("ok", "API 在线");
    markRefresh();
  } catch (err) {
    setApi("err", "API 异常");
    toast(err.message);
  }
}

function stopPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
}

async function pollPhotoRequest(requestId) {
  try {
    const item = await apiGet(`/api/device/photoRequest/${encodeURIComponent(requestId)}`);
    const index = state.photoRequests.findIndex((row) => row.requestId === requestId);
    if (index >= 0) state.photoRequests[index] = item;
    else state.photoRequests.unshift(item);
    renderPhotoRequests();
    $("cameraRequestMeta").textContent = `${photoStatusLabel(item.stat)} · 请求于 ${formatDateTime(item.requestedAt)}`;
    if (item.stat === "uploaded") {
      showPhoto(item);
      stopPolling();
      $("requestCameraBtn").disabled = false;
      toast("树莓派画面已返回");
    } else if (["failed", "expired", "cancelled"].includes(item.stat)) {
      stopPolling();
      $("requestCameraBtn").disabled = false;
      toast(item.errorMessage || `照片请求${photoStatusLabel(item.stat)}`);
    }
  } catch (err) {
    stopPolling();
    $("requestCameraBtn").disabled = false;
    toast(err.message);
  }
}

async function requestCamera() {
  try {
    const button = $("requestCameraBtn");
    button.disabled = true;
    const request = await apiSend("/api/device/pi/photoRequest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "Web 工作台请求当前摄像头画面", ttlSeconds: 300 }),
    });
    state.activeRequestId = request.requestId;
    state.photoRequests.unshift(request);
    renderPhotoRequests();
    $("cameraRequestMeta").textContent = "请求已创建，等待树莓派下一次心跳领取";
    stopPolling();
    await pollPhotoRequest(request.requestId);
    state.pollTimer = setInterval(() => pollPhotoRequest(request.requestId), 2000);
  } catch (err) {
    $("requestCameraBtn").disabled = false;
    toast(err.message);
  }
}

$("refreshDeviceBtn")?.addEventListener("click", refreshDevice);
$("requestCameraBtn")?.addEventListener("click", requestCamera);
$("deviceLogSearch")?.addEventListener("input", renderLogs);
document.body.addEventListener("click", (event) => {
  const button = event.target.closest("[data-view-photo]");
  if (!button) return;
  const item = state.photoRequests.find((row) => row.requestId === button.dataset.viewPhoto);
  if (item) showPhoto(item);
});

loadTopUser();
refreshDevice();
setInterval(refreshDevice, 10000);
