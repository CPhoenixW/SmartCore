import { deviceStateView, formatDateTime } from "./work_shared.js";

const $ = (id) => document.getElementById(id);
const state = {
  logs: [],
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
  if ($("lastRefresh")) {
    $("lastRefresh").textContent = "更新于 " + new Date().toLocaleTimeString("zh-CN", { hour12: false });
  }
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

function percent(numerator, denominator) {
  if (!denominator) return "—";
  return `${Math.round((numerator / denominator) * 100)}%`;
}

function renderUsageAnalysis() {
  const cutoff = Date.now() - 24 * 3600_000;
  const rows = state.logs.filter((row) => {
    if (row.deviceId !== "pi" || !row.seenAt) return false;
    const time = new Date(row.seenAt).getTime();
    return Number.isFinite(time) && time >= cutoff;
  });

  const working = rows.filter((row) => row.state === "working").length;
  const present = rows.filter((row) => Boolean(row.meta?.present)).length;
  const confidences = rows.map((row) => Number(row.confidence)).filter(Number.isFinite);
  const averageConfidence = confidences.length
    ? confidences.reduce((sum, value) => sum + value, 0) / confidences.length
    : null;

  const people = new Map();
  const hours = new Map();
  const states = new Map([["working", 0], ["away", 0], ["unknown", 0], ["offline", 0]]);
  rows.forEach((row) => {
    const current = states.get(row.state) || 0;
    states.set(row.state || "unknown", current + 1);
    const hour = new Date(row.seenAt).getHours();
    hours.set(hour, (hours.get(hour) || 0) + 1);
    const persons = Array.isArray(row.meta?.persons) ? row.meta.persons : [];
    persons.forEach((person) => {
      const name = person.name || person.personId;
      if (name) people.set(name, (people.get(name) || 0) + 1);
    });
  });

  const topPerson = [...people.entries()].sort((a, b) => b[1] - a[1])[0];
  const peakHour = [...hours.entries()].sort((a, b) => b[1] - a[1])[0];

  $("usageSamples").textContent = String(rows.length);
  $("usageWorkingRate").textContent = percent(working, rows.length);
  $("usagePresentRate").textContent = percent(present, rows.length);
  $("usageConfidence").textContent = averageConfidence == null ? "—" : `${Math.round(averageConfidence * 100)}%`;
  $("usageTopPerson").textContent = topPerson ? `${topPerson[0]} · ${topPerson[1]} 次` : "暂无识别";
  $("usagePeakHour").textContent = peakHour ? `${String(peakHour[0]).padStart(2, "0")}:00–${String((peakHour[0] + 1) % 24).padStart(2, "0")}:00` : "暂无数据";

  const labels = { working: "工作中", away: "离开", unknown: "未知", offline: "离线" };
  const order = ["working", "away", "unknown", "offline"];
  $("usageStateBars").innerHTML = rows.length
    ? order.map((key) => {
      const count = states.get(key) || 0;
      const width = Math.round((count / rows.length) * 100);
      return `<div class="usage-bar-row"><div class="usage-bar-label"><span>${labels[key]}</span><strong>${width}%</strong></div><div class="usage-bar-track"><span class="usage-bar-fill ${key}" style="width:${width}%"></span></div></div>`;
    }).join("")
    : '<div class="empty compact-empty">近 24 小时暂无可分析的状态记录</div>';
}

function setCameraPending(pending) {
  $("requestCameraBtn").disabled = pending;
  const frame = $("cameraFrame");
  frame.classList.toggle("camera-frame-pending", pending);
  if (pending) {
    $("cameraEmpty").hidden = false;
    $("cameraEmpty").querySelector("strong").textContent = "正在等待树莓派回传";
    $("cameraEmpty").querySelector("span").textContent = "请求已创建，通常会在下一次 10 秒心跳后返回";
  }
}

function restoreCameraEmpty() {
  const frame = $("cameraFrame");
  frame.classList.remove("has-image", "camera-frame-pending");
  frame.classList.add("camera-frame-empty");
  $("cameraImage").hidden = true;
  $("cameraImage").removeAttribute("src");
  $("cameraEmpty").hidden = false;
  $("cameraEmpty").querySelector("strong").textContent = "等待请求当前画面";
  $("cameraEmpty").querySelector("span").textContent = "点击右上角按钮，树莓派会在下一次心跳上传一帧图像";
}

function showPhoto(item) {
  if (!item?.imageAvailable || !item.imageUrl) return;
  const frame = $("cameraFrame");
  const image = $("cameraImage");
  image.src = `${item.imageUrl}?t=${Date.now()}`;
  image.hidden = false;
  $("cameraEmpty").hidden = true;
  frame.classList.remove("camera-frame-empty", "camera-frame-pending");
  frame.classList.add("has-image");
  $("cameraRequestMeta").textContent = `拍摄于 ${formatDateTime(item.capturedAt)} · ${Math.max(1, Math.round((item.imageSize || 0) / 1024))} KB`;
}

async function refreshDevice() {
  try {
    setApi("busy", "API 请求中");
    const logs = await apiGet("/api/devState?devId=pi&limit=1000");
    state.logs = Array.isArray(logs) ? logs : [];
    renderCurrentState();
    renderLogs();
    renderUsageAnalysis();
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
    $("cameraRequestMeta").textContent = item.stat === "pending"
      ? `等待树莓派领取 · 请求于 ${formatDateTime(item.requestedAt)}`
      : `状态：${item.stat}`;
    if (item.stat === "uploaded") {
      showPhoto(item);
      state.activeRequestId = null;
      stopPolling();
      setCameraPending(false);
      toast("树莓派画面已返回");
      return true;
    }
    if (["failed", "expired", "cancelled"].includes(item.stat)) {
      state.activeRequestId = null;
      stopPolling();
      setCameraPending(false);
      restoreCameraEmpty();
      $("cameraRequestMeta").textContent = item.errorMessage || `请求${item.stat}`;
      toast(item.errorMessage || `照片请求${item.stat}`);
      return true;
    }
    return false;
  } catch (err) {
    state.activeRequestId = null;
    stopPolling();
    setCameraPending(false);
    restoreCameraEmpty();
    $("cameraRequestMeta").textContent = "画面请求失败";
    toast(err.message);
    return true;
  }
}

async function requestCamera() {
  if (state.activeRequestId) return;
  try {
    restoreCameraEmpty();
    setCameraPending(true);
    const request = await apiSend("/api/device/pi/photoRequest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "Web 工作台请求当前摄像头画面", ttlSeconds: 300 }),
    });
    state.activeRequestId = request.requestId;
    $("cameraRequestMeta").textContent = "请求已创建，等待树莓派下一次心跳领取";
    stopPolling();
    const finished = await pollPhotoRequest(request.requestId);
    if (!finished && state.activeRequestId === request.requestId) {
      state.pollTimer = setInterval(() => pollPhotoRequest(request.requestId), 2000);
    }
  } catch (err) {
    state.activeRequestId = null;
    setCameraPending(false);
    restoreCameraEmpty();
    $("cameraRequestMeta").textContent = "当前没有进行中的画面请求";
    toast(err.message);
  }
}

$("refreshDeviceBtn")?.addEventListener("click", refreshDevice);
$("requestCameraBtn")?.addEventListener("click", requestCamera);
$("deviceLogSearch")?.addEventListener("input", renderLogs);

loadTopUser();
restoreCameraEmpty();
refreshDevice();
setInterval(refreshDevice, 10000);
