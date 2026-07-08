import {
  deviceStateView,
  formatDateTime,
  formatMinutes,
  formatRecordCount,
  getUiLanguage,
  t,
} from "./work_shared.js";

const $ = (id) => document.getElementById(id);
const state = {
  latestState: null,
  logs: [],
  usage: null,
  activeRequestId: null,
  pollTimer: null,
  chartPositioned: false,
};

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;");
}

function ui(zh, en) {
  return getUiLanguage() === "en" ? en : zh;
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

function markRefresh() {
  if ($("lastRefresh")) {
    $("lastRefresh").textContent = ui(
      `更新于 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`,
      `Updated at ${new Date().toLocaleTimeString("en-US", { hour12: false })}`,
    );
  }
}

async function apiGet(path) {
  const response = await fetch(path, { cache: "no-store" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.ok === false) {
    throw new Error(body.detail || body.msg || `HTTP ${response.status}`);
  }
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
    if (text) text.textContent = avatarText(user?.displayName);
    if (img && user?.avatarUrl) {
      img.src = user.avatarUrl;
      img.hidden = false;
      if (text) text.hidden = true;
    }
  } catch {
    if ($("topAvatarText")) $("topAvatarText").textContent = "SC";
  }
}

function personNames(view) {
  return view.persons.map((person) => person.name || person.personId).filter(Boolean);
}

function renderCurrentState() {
  const view = deviceStateView(state.latestState, Number.MAX_SAFE_INTEGER);
  $("deviceStateDot").className = `device-state-dot ${view.state}`;
  $("deviceStateTitle").textContent = view.label;
  $("deviceStateSeen").textContent = view.seenAt
    ? ui(`数据库最后状态：${formatDateTime(view.seenAt)}`, `Last cached state: ${formatDateTime(view.seenAt)}`)
    : t("尚未收到树莓派回传");
  $("devicePresent").textContent = view.present ? t("有人") : t("无人");
  const names = personNames(view);
  $("devicePersons").textContent = names.length ? names.join(ui("、", ", ")) : t("未识别");
  $("deviceConfidence").textContent = view.confidence == null
    ? "—"
    : `${Math.round(Number(view.confidence) * 100)}%`;
  const skew = Number(view.meta.clockSkewSeconds);
  $("deviceClockSkew").textContent = Number.isFinite(skew)
    ? ui(`${skew >= 0 ? "+" : ""}${skew.toFixed(2)} 秒`, `${skew >= 0 ? "+" : ""}${skew.toFixed(2)} s`)
    : "—";
  $("deviceModel").textContent = view.meta.model || "—";
  $("deviceCamera").textContent = view.meta.camera || "—";
}

function logText(row) {
  const meta = row.meta && typeof row.meta === "object" ? row.meta : {};
  return `${row.state || ""} ${row.seenAt || ""} ${JSON.stringify(meta)}`.toLowerCase();
}

function renderLogs() {
  const query = $("deviceLogSearch")?.value.trim().toLowerCase() || "";
  const rows = state.logs.filter((row) => !query || logText(row).includes(query));
  $("deviceLogCount").textContent = formatRecordCount(rows.length);
  $("deviceLogList").innerHTML = rows.length
    ? rows.map((row) => {
      const view = deviceStateView(row, Number.MAX_SAFE_INTEGER);
      const names = personNames(view);
      const confidence = row.confidence == null ? "—" : `${Math.round(Number(row.confidence) * 100)}%`;
      const personLabel = names.length ? names.join(ui("、", ", ")) : t("未识别人物");
      const confidenceLabel = ui(`置信度 ${confidence}`, `Confidence ${confidence}`);
      return `<details class="log-row device-log-row"><summary><span class="row-title"><span class="device-state-dot ${esc(row.state || "unknown")}"></span>${esc(view.label)} · ${esc(personLabel)}</span><span class="row-meta">${esc(formatDateTime(row.seenAt))} · ${esc(confidenceLabel)}</span></summary><pre class="log-json">${esc(JSON.stringify(row, null, 2))}</pre></details>`;
    }).join("")
    : `<div class="empty">${esc(t("暂无树莓派识别日志"))}</div>`;
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

function ensureChartHint() {
  const wrap = $("usageChartWrap");
  if (!wrap || wrap.nextElementSibling?.classList.contains("usage-chart-hint")) return;
  const hint = document.createElement("div");
  hint.className = "usage-chart-hint";
  hint.textContent = t("左右滑动查看其他时段");
  wrap.insertAdjacentElement("afterend", hint);
}

function positionChart(hour) {
  if (state.chartPositioned) return;
  const wrap = $("usageChartWrap");
  const svg = $("usageHourlyChart");
  if (!wrap || !svg || svg.hidden) return;
  requestAnimationFrame(() => {
    const graphWidth = svg.getBoundingClientRect().width;
    const targetX = (Math.max(0, Math.min(23, hour)) / 23) * graphWidth;
    wrap.scrollLeft = Math.max(0, targetX - wrap.clientWidth * 0.58);
    state.chartPositioned = true;
  });
}

function renderHourlyChart(hourly, hasData, peakHour) {
  const svg = $("usageHourlyChart");
  const empty = $("usageChartEmpty");
  if (!svg || !empty) return;

  ensureChartHint();
  empty.hidden = hasData;
  svg.hidden = !hasData;
  if (!hasData) {
    svg.innerHTML = "";
    return;
  }

  const width = 1920;
  const height = 280;
  const left = 58;
  const right = 34;
  const top = 18;
  const bottom = 42;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const x = (hour) => left + (hour / 23) * plotWidth;
  const y = (minutes) => top + plotHeight - (Math.min(60, Math.max(0, minutes)) / 60) * plotHeight;
  const points = hourly.map((minutes, hour) => ({ x: x(hour), y: y(minutes), minutes, hour }));
  const linePath = smoothPath(points);
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${top + plotHeight} L ${points[0].x} ${top + plotHeight} Z`;
  const nowHour = new Date().getHours() + new Date().getMinutes() / 60;
  const nowX = x(Math.min(23, nowHour));

  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const yTicks = [0, 15, 30, 45, 60];
  const grid = yTicks.map((tick) => {
    const py = y(tick);
    return `<line x1="${left}" y1="${py}" x2="${width - right}" y2="${py}" class="usage-grid-line"/><text x="${left - 12}" y="${py + 4}" class="usage-axis-label" text-anchor="end">${tick}</text>`;
  }).join("");
  const hourGuides = Array.from({ length: 24 }, (_, hour) => {
    const px = x(hour);
    return `<line x1="${px}" y1="${top}" x2="${px}" y2="${top + plotHeight}" class="usage-hour-guide"/><text x="${px}" y="${height - 14}" class="usage-axis-label" text-anchor="middle">${String(hour).padStart(2, "0")}:00</text>`;
  }).join("");
  const dots = points
    .filter((point) => point.minutes > 0)
    .map((point, index) => `<circle cx="${point.x}" cy="${point.y}" r="4" class="usage-line-point" style="animation-delay:${420 + index * 45}ms"><title>${String(point.hour).padStart(2, "0")}:00 · ${formatMinutes(point.minutes)}</title></circle>`)
    .join("");

  svg.innerHTML = `
    <defs>
      <linearGradient id="usageAreaGradient" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#2563eb" stop-opacity="0.24"/>
        <stop offset="100%" stop-color="#2563eb" stop-opacity="0.02"/>
      </linearGradient>
    </defs>
    ${grid}
    ${hourGuides}
    <path d="${areaPath}" class="usage-line-area"/>
    <path d="${linePath}" class="usage-line-path"/>
    ${dots}
    <line x1="${nowX}" y1="${top}" x2="${nowX}" y2="${top + plotHeight}" class="usage-now-marker"/>
    <text x="${nowX + 7}" y="${top + 13}" class="usage-now-label">${ui("现在", "Now")}</text>
  `;

  positionChart(peakHour ?? new Date().getHours());
}

function renderUsageAnalysis() {
  const usage = state.usage || {};
  const hourly = Array.isArray(usage.hourlyMinutes)
    ? usage.hourlyMinutes.map((value) => Number(value) || 0)
    : Array(24).fill(0);
  const hasData = Number(usage.sampleCount || 0) > 0;
  $("usageTodayMinutes").textContent = formatMinutes(usage.totalMinutes || 0);
  $("usagePeakHour").textContent = Number.isInteger(usage.peakHour)
    ? `${String(usage.peakHour).padStart(2, "0")}:00–${String((usage.peakHour + 1) % 24).padStart(2, "0")}:00`
    : "—";
  $("usageConfidence").textContent = usage.averageConfidence == null
    ? "—"
    : `${Math.round(Number(usage.averageConfidence) * 100)}%`;
  renderHourlyChart(hourly, hasData, usage.peakHour);
}

function bindChartDrag() {
  const wrap = $("usageChartWrap");
  if (!wrap || wrap.dataset.dragBound === "1") return;
  wrap.dataset.dragBound = "1";
  let dragging = false;
  let startX = 0;
  let startScroll = 0;

  wrap.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "touch") return;
    dragging = true;
    startX = event.clientX;
    startScroll = wrap.scrollLeft;
    wrap.classList.add("dragging");
    wrap.setPointerCapture(event.pointerId);
  });
  wrap.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    wrap.scrollLeft = startScroll - (event.clientX - startX);
  });
  const stop = (event) => {
    if (!dragging) return;
    dragging = false;
    wrap.classList.remove("dragging");
    if (wrap.hasPointerCapture(event.pointerId)) wrap.releasePointerCapture(event.pointerId);
  };
  wrap.addEventListener("pointerup", stop);
  wrap.addEventListener("pointercancel", stop);
  wrap.addEventListener("pointerleave", (event) => {
    if (dragging && event.buttons === 0) stop(event);
  });
}

async function refreshLatestState({ announce = false } = {}) {
  if (announce) setApi("busy", "API 请求中");
  state.latestState = await apiGet("/api/devState/latest?devId=pi");
  renderCurrentState();
  if (announce) {
    setApi("ok", "API 在线");
    markRefresh();
  }
}

async function refreshRecentLogs() {
  const rows = await apiGet("/api/devState/recent?devId=pi&limit=240");
  state.logs = Array.isArray(rows) ? rows : [];
  renderLogs();
}

async function refreshUsage() {
  state.usage = await apiGet("/api/devState/usage/today?devId=pi&timezone=Asia%2FShanghai");
  renderUsageAnalysis();
}

async function refreshDevice() {
  setApi("busy", "API 请求中");
  const latestResult = await Promise.allSettled([
    refreshLatestState(),
    refreshRecentLogs(),
    refreshUsage(),
  ]);
  const failed = latestResult.find((result) => result.status === "rejected");
  if (failed) {
    setApi("err", "API 异常");
    toast(failed.reason?.message || ui("设备数据加载失败", "Failed to load device data"));
    return;
  }
  setApi("ok", "API 在线");
  markRefresh();
}

async function initialDeviceLoad() {
  setApi("busy", "API 请求中");
  try {
    await refreshLatestState();
    setApi("ok", "API 在线");
    markRefresh();
  } catch (error) {
    setApi("err", "API 异常");
    toast(error.message);
  }
  Promise.allSettled([refreshRecentLogs(), refreshUsage()]).then((results) => {
    if (results.every((result) => result.status === "fulfilled")) {
      setApi("ok", "API 在线");
      markRefresh();
    }
  });
}

function setCameraPending(pending) {
  $("requestCameraBtn").disabled = pending;
  const frame = $("cameraFrame");
  frame.classList.toggle("camera-frame-pending", pending);
  if (pending) {
    $("cameraEmpty").hidden = false;
    $("cameraEmpty").querySelector("strong").textContent = ui("正在等待树莓派回传", "Waiting for Raspberry Pi");
    $("cameraEmpty").querySelector("span").textContent = ui(
      "请求已创建，通常会在下一次 10 秒心跳后返回",
      "The request usually completes after the next 10-second heartbeat",
    );
  }
}

function restoreCameraEmpty() {
  const frame = $("cameraFrame");
  frame.classList.remove("has-image", "camera-frame-pending");
  frame.classList.add("camera-frame-empty");
  $("cameraImage").hidden = true;
  $("cameraImage").removeAttribute("src");
  $("cameraEmpty").hidden = false;
  $("cameraEmpty").querySelector("strong").textContent = t("等待请求当前画面");
  $("cameraEmpty").querySelector("span").textContent = ui(
    "点击右上角按钮，树莓派会在下一次心跳上传一帧图像",
    "Use the button above to request a frame on the next heartbeat",
  );
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
  $("cameraRequestMeta").textContent = ui(
    `拍摄于 ${formatDateTime(item.capturedAt)} · ${Math.max(1, Math.round((item.imageSize || 0) / 1024))} KB`,
    `Captured at ${formatDateTime(item.capturedAt)} · ${Math.max(1, Math.round((item.imageSize || 0) / 1024))} KB`,
  );
}

function stopPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
}

async function pollPhotoRequest(requestId) {
  try {
    const item = await apiGet(`/api/device/photoRequest/${encodeURIComponent(requestId)}`);
    $("cameraRequestMeta").textContent = item.stat === "pending"
      ? ui(`等待树莓派领取 · 请求于 ${formatDateTime(item.requestedAt)}`, `Waiting for Raspberry Pi · requested ${formatDateTime(item.requestedAt)}`)
      : ui(`状态：${item.stat}`, `Status: ${item.stat}`);
    if (item.stat === "uploaded") {
      showPhoto(item);
      state.activeRequestId = null;
      stopPolling();
      setCameraPending(false);
      toast(ui("树莓派画面已返回", "Raspberry Pi frame received"));
      return true;
    }
    if (["failed", "expired", "cancelled"].includes(item.stat)) {
      state.activeRequestId = null;
      stopPolling();
      setCameraPending(false);
      restoreCameraEmpty();
      $("cameraRequestMeta").textContent = item.errorMessage || item.stat;
      toast(item.errorMessage || item.stat);
      return true;
    }
    return false;
  } catch (error) {
    state.activeRequestId = null;
    stopPolling();
    setCameraPending(false);
    restoreCameraEmpty();
    $("cameraRequestMeta").textContent = ui("画面请求失败", "Frame request failed");
    toast(error.message);
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
    $("cameraRequestMeta").textContent = ui(
      "请求已创建，等待树莓派下一次心跳领取",
      "Request created; waiting for the next Raspberry Pi heartbeat",
    );
    stopPolling();
    const finished = await pollPhotoRequest(request.requestId);
    if (!finished && state.activeRequestId === request.requestId) {
      state.pollTimer = setInterval(() => pollPhotoRequest(request.requestId), 2000);
    }
  } catch (error) {
    state.activeRequestId = null;
    setCameraPending(false);
    restoreCameraEmpty();
    $("cameraRequestMeta").textContent = t("当前没有进行中的画面请求");
    toast(error.message);
  }
}

function rerenderLocalizedDeviceUi() {
  renderCurrentState();
  renderLogs();
  state.chartPositioned = false;
  renderUsageAnalysis();
  restoreCameraEmpty();
  ensureChartHint();
}

$("refreshDeviceBtn")?.addEventListener("click", refreshDevice);
$("requestCameraBtn")?.addEventListener("click", requestCamera);
$("deviceLogSearch")?.addEventListener("input", renderLogs);
window.addEventListener("smartcore:languagechange", rerenderLocalizedDeviceUi);

loadTopUser();
restoreCameraEmpty();
bindChartDrag();
initialDeviceLoad();
setInterval(() => refreshLatestState().catch(() => {}), 10000);
setInterval(() => {
  Promise.allSettled([refreshRecentLogs(), refreshUsage()]);
}, 60000);
