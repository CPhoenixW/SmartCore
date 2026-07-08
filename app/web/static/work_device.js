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
  const rows = state.logs
    .filter((row) => row.deviceId === "pi" && (!query || logText(row).includes(query)))
    .slice(0, 240);
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

function startOfToday(now = new Date()) {
  return new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, 0);
}

function splitMinutesIntoHours(hourly, startMs, endMs) {
  let cursor = startMs;
  while (cursor < endMs) {
    const cursorDate = new Date(cursor);
    const hour = cursorDate.getHours();
    const nextHour = new Date(
      cursorDate.getFullYear(),
      cursorDate.getMonth(),
      cursorDate.getDate(),
      hour + 1,
      0,
      0,
      0,
    ).getTime();
    const segmentEnd = Math.min(endMs, nextHour);
    hourly[hour] += (segmentEnd - cursor) / 60000;
    cursor = segmentEnd;
  }
}

function calculateHourlyUsage() {
  const now = new Date();
  const todayStart = startOfToday(now).getTime();
  const valid = state.logs
    .filter((row) => row.deviceId === "pi" && row.seenAt)
    .map((row) => ({ row, time: new Date(row.seenAt).getTime() }))
    .filter((item) => Number.isFinite(item.time) && item.time <= now.getTime())
    .sort((a, b) => a.time - b.time);

  const previous = valid.filter((item) => item.time < todayStart).pop();
  const today = valid.filter((item) => item.time >= todayStart);
  const timeline = previous ? [previous, ...today] : today;
  const hourly = Array(24).fill(0);

  timeline.forEach((item, index) => {
    if (item.row.state !== "working") return;
    const nextTime = timeline[index + 1]?.time ?? now.getTime();
    const start = Math.max(item.time, todayStart);
    const rawEnd = Math.min(nextTime, now.getTime());
    const end = Math.min(rawEnd, start + 120000);
    if (end > start) splitMinutesIntoHours(hourly, start, end);
  });

  const rowsToday = today.map((item) => item.row);
  const confidences = rowsToday
    .map((row) => Number(row.confidence))
    .filter(Number.isFinite);
  const averageConfidence = confidences.length
    ? confidences.reduce((sum, value) => sum + value, 0) / confidences.length
    : null;

  return {
    hourly,
    rowsToday,
    averageConfidence,
    totalMinutes: hourly.reduce((sum, value) => sum + value, 0),
  };
}

function smoothPath(points) {
  if (!points.length) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
  let path = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length; i += 1) {
    const previous = points[i - 1];
    const current = points[i];
    const midX = (previous.x + current.x) / 2;
    path += ` C ${midX} ${previous.y}, ${midX} ${current.y}, ${current.x} ${current.y}`;
  }
  return path;
}

function renderHourlyChart(hourly, hasData) {
  const svg = $("usageHourlyChart");
  const empty = $("usageChartEmpty");
  if (!svg || !empty) return;

  empty.hidden = hasData;
  svg.hidden = !hasData;
  if (!hasData) {
    svg.innerHTML = "";
    return;
  }

  const width = 720;
  const height = 270;
  const left = 46;
  const right = 16;
  const top = 18;
  const bottom = 38;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const x = (hour) => left + (hour / 23) * plotWidth;
  const y = (minutes) => top + plotHeight - (Math.min(60, Math.max(0, minutes)) / 60) * plotHeight;
  const points = hourly.map((minutes, hour) => ({ x: x(hour), y: y(minutes), minutes, hour }));
  const linePath = smoothPath(points);
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${top + plotHeight} L ${points[0].x} ${top + plotHeight} Z`;

  const yTicks = [0, 15, 30, 45, 60];
  const grid = yTicks.map((tick) => {
    const py = y(tick);
    return `<line x1="${left}" y1="${py}" x2="${width - right}" y2="${py}" class="usage-grid-line"/><text x="${left - 10}" y="${py + 4}" class="usage-axis-label" text-anchor="end">${tick}</text>`;
  }).join("");
  const xLabels = Array.from({ length: 8 }, (_, index) => index * 3).map((hour) => `<text x="${x(hour)}" y="${height - 12}" class="usage-axis-label" text-anchor="middle">${String(hour).padStart(2, "0")}</text>`).join("");
  const dots = points
    .filter((point) => point.minutes > 0)
    .map((point) => `<circle cx="${point.x}" cy="${point.y}" r="4" class="usage-line-point"><title>${String(point.hour).padStart(2, "0")}:00 · ${Math.round(point.minutes)} 分钟</title></circle>`)
    .join("");

  svg.innerHTML = `
    <defs>
      <linearGradient id="usageAreaGradient" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#2563eb" stop-opacity="0.24"/>
        <stop offset="100%" stop-color="#2563eb" stop-opacity="0.02"/>
      </linearGradient>
    </defs>
    ${grid}
    ${xLabels}
    <path d="${areaPath}" class="usage-line-area"/>
    <path d="${linePath}" class="usage-line-path"/>
    ${dots}
  `;
}

function renderUsageAnalysis() {
  const result = calculateHourlyUsage();
  const peakMinutes = Math.max(...result.hourly);
  const peakHour = peakMinutes > 0 ? result.hourly.indexOf(peakMinutes) : -1;
  $("usageTodayMinutes").textContent = `${Math.round(result.totalMinutes)} 分钟`;
  $("usagePeakHour").textContent = peakHour >= 0
    ? `${String(peakHour).padStart(2, "0")}:00–${String((peakHour + 1) % 24).padStart(2, "0")}:00`
    : "—";
  $("usageConfidence").textContent = result.averageConfidence == null
    ? "—"
    : `${Math.round(result.averageConfidence * 100)}%`;
  renderHourlyChart(result.hourly, result.rowsToday.length > 0);
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
    const logs = await apiGet("/api/devState?devId=pi&limit=3000");
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
