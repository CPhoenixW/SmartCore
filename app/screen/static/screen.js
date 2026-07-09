(function () {
  const wsProto = location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${wsProto}//${location.host}/screen/ws`;
  const shellEl = document.querySelector(".screen-shell");
  const clockHoursEl = document.getElementById("clockHours");
  const clockSepEl = document.getElementById("clockSep");
  const clockMinsEl = document.getElementById("clockMins");
  const clockDateEl = document.getElementById("clockDate");
  const stateEl = document.getElementById("currentState");
  const stateCaptionEl = document.getElementById("stateCaption");
  const stateRowEl = document.querySelector(".state-row");
  const currentListEl = document.getElementById("latestReminderList");
  const todayEvtListEl = document.getElementById("todayEvtList");
  const overdueListEl = document.getElementById("expiredReminderList");
  const wsStatusEl = document.getElementById("wsStatus");
  const wsStatusText = document.getElementById("wsStatusText");
  const lastMsgAt = document.getElementById("lastMsgAt");
  const reminderPageEl = document.getElementById("reminderPage");
  const reminderPageTitleEl = document.getElementById("reminderPageTitle");
  const reminderPageContentEl = document.getElementById("reminderPageContent");
  const reminderDoneEl = document.getElementById("reminderDone");
  const reminderSnoozeEl = document.getElementById("reminderSnooze");

  let ws = null;
  let reconnectTimer = null;
  let serverOffsetMs = 0;
  let currentMode = "away";
  let audioCtx = null;
  let activeReminder = null;
  let expireTimer = null;
  let cachedEvents = [];

  function setWsConnected(connected) {
    wsStatusEl?.classList.toggle("connected", connected);
    if (wsStatusText) wsStatusText.textContent = connected ? "已连接" : "离线";
  }

  function formatDate(now) {
    return now.toLocaleDateString("zh-CN", {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  }

  function nowDate() {
    return new Date(Date.now() + serverOffsetMs);
  }

  function tickClock() {
    const now = nowDate();
    const h = String(now.getHours()).padStart(2, "0");
    const m = String(now.getMinutes()).padStart(2, "0");
    if (clockHoursEl) clockHoursEl.textContent = h;
    if (clockMinsEl) clockMinsEl.textContent = m;
    clockSepEl?.classList.toggle("blink-off", now.getSeconds() % 2 === 1);
    if (clockDateEl) clockDateEl.textContent = formatDate(now);
    renderSchedule(cachedEvents);
  }

  const STATE_CAPTIONS = {
    working: "专注工作中",
    away: "暂时离开",
    offline: "设备离线",
    unknown: "状态未知",
  };

  function applyLayoutMode(state) {
    const working = state === "working";
    const mode = working ? "working" : "away";
    const changed = currentMode !== mode;
    currentMode = mode;
    if (shellEl) {
      shellEl.dataset.mode = mode;
      shellEl.classList.toggle("mode-working", working);
      shellEl.classList.toggle("mode-away", !working);
    }
    if (stateRowEl) stateRowEl.hidden = !working;
    if (changed) tickClock();
  }

  function renderState(state) {
    const next = state || "unknown";
    if (stateEl) {
      stateEl.textContent = next;
      stateEl.className = next;
    }
    if (stateCaptionEl) stateCaptionEl.textContent = STATE_CAPTIONS[next] || next;
    applyLayoutMode(next);
  }

  function eventStart(evt) {
    return evt?.evtType === "plan" && evt.stTime ? new Date(evt.stTime) : null;
  }

  function eventEnd(evt) {
    const start = eventStart(evt);
    if (!start) return null;
    return new Date(start.getTime() + Number(evt.durationMin || 0) * 60000);
  }

  function sameDay(a, b) {
    return Boolean(
      a && b &&
      a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() &&
      a.getDate() === b.getDate()
    );
  }

  function fmtTime(date) {
    if (!date || Number.isNaN(date.getTime())) return "--:--";
    return date.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }

  function eventTimeLabel(evt) {
    const start = eventStart(evt);
    const end = eventEnd(evt);
    if (start && end) return `${fmtTime(start)}-${fmtTime(end)}`;
    return fmtTime(start);
  }

  function isOngoing(evt, now) {
    const start = eventStart(evt);
    const end = eventEnd(evt);
    return Boolean(start && end && start <= now && end >= now);
  }

  function isOverdue(evt, now) {
    const end = eventEnd(evt);
    return Boolean(evt.stat === "todo" && end && end < now);
  }

  function isTodayEvt(evt, now) {
    const start = eventStart(evt);
    const end = eventEnd(evt);
    return Boolean((start && sameDay(start, now)) || (end && sameDay(end, now)));
  }

  function clearList(el) {
    if (!el) return;
    el.innerHTML = "";
    el.classList.remove("empty");
  }

  function setEmpty(el) {
    if (!el) return;
    el.innerHTML = "";
    el.classList.add("empty");
  }

  function renderCurrent(events) {
    clearList(currentListEl);
    if (!events.length) return setEmpty(currentListEl);
    events.forEach((evt) => {
      const card = document.createElement("article");
      card.className = "today-primary";
      card.innerHTML = '<div class="today-time"></div><h2></h2>';
      card.querySelector(".today-time").textContent = eventTimeLabel(evt);
      card.querySelector("h2").textContent = evt.title || "未命名计划";
      currentListEl?.appendChild(card);
    });
  }

  function renderCompactList(el, events) {
    clearList(el);
    if (!events.length) return setEmpty(el);
    events.forEach((evt) => {
      const card = document.createElement("article");
      card.className = "today-compact";
      card.innerHTML = '<span class="today-chip"></span><strong></strong>';
      card.querySelector(".today-chip").textContent = `计划 ${eventTimeLabel(evt)}`;
      card.querySelector("strong").textContent = evt.title || "未命名计划";
      el?.appendChild(card);
    });
  }

  function renderOverdue(events) {
    clearList(overdueListEl);
    if (!events.length) return setEmpty(overdueListEl);
    events.forEach((evt) => {
      const row = document.createElement("article");
      row.className = "expired-reminder";
      row.innerHTML = "<strong></strong><span></span>";
      row.querySelector("strong").textContent = evt.title || "未命名计划";
      row.querySelector("span").textContent = `计划 · ${eventTimeLabel(evt)}`;
      overdueListEl?.appendChild(row);
    });
  }

  function renderSchedule(events) {
    const now = nowDate();
    const todo = (events || []).filter((evt) => evt.evtType === "plan" && evt.stat === "todo");
    const current = todo.filter((evt) => isOngoing(evt, now)).sort((a, b) => eventEnd(a) - eventEnd(b));
    const overdue = todo.filter((evt) => isOverdue(evt, now)).sort((a, b) => eventEnd(a) - eventEnd(b));
    const otherToday = todo
      .filter((evt) => isTodayEvt(evt, now) && !isOngoing(evt, now) && !isOverdue(evt, now))
      .sort((a, b) => eventStart(a) - eventStart(b));
    renderCurrent(current);
    renderCompactList(todayEvtListEl, otherToday);
    renderOverdue(overdue);
  }

  async function loadTodayEvents() {
    try {
      const resp = await fetch("/api/planEvt");
      const data = await resp.json();
      cachedEvents = (data.data || []).filter((evt) => evt.evtType === "plan");
      renderSchedule(cachedEvents);
    } catch {
      cachedEvents = [];
      setEmpty(currentListEl);
      setEmpty(todayEvtListEl);
      setEmpty(overdueListEl);
    }
  }

  function getAudioCtx() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    if (!audioCtx) audioCtx = new Ctx();
    return audioCtx;
  }

  function playReminderSound() {
    const ctx = getAudioCtx();
    if (!ctx) return;
    ctx.resume?.();
    const now = ctx.currentTime;
    [0, 0.18, 0.36].forEach((offset) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(880, now + offset);
      gain.gain.setValueAtTime(0.0001, now + offset);
      gain.gain.exponentialRampToValueAtTime(0.16, now + offset + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + 0.16);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now + offset);
      osc.stop(now + offset + 0.16);
    });
  }

  function clearExpireTimer() {
    if (expireTimer) {
      clearTimeout(expireTimer);
      expireTimer = null;
    }
  }

  function hideReminderPage() {
    reminderPageEl?.classList.remove("show");
    reminderPageEl?.setAttribute("aria-hidden", "true");
    clearExpireTimer();
  }

  function showReminderPage(title, content, evtId) {
    activeReminder = { title, content, evtId: evtId || null };
    if (reminderPageTitleEl) reminderPageTitleEl.textContent = title || "提醒";
    if (reminderPageContentEl) reminderPageContentEl.textContent = content || "";
    reminderPageEl?.classList.add("show");
    reminderPageEl?.setAttribute("aria-hidden", "false");
    loadTodayEvents();
    playReminderSound();
    clearExpireTimer();
    expireTimer = setTimeout(expireActiveReminder, 60000);
  }

  function expireActiveReminder() {
    if (!activeReminder) return;
    activeReminder = null;
    hideReminderPage();
    loadTodayEvents();
  }

  async function submitReminderAction(action) {
    if (!activeReminder?.evtId) {
      hideReminderPage();
      activeReminder = null;
      return;
    }
    try {
      await fetch("/api/reminder/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ evtId: activeReminder.evtId, action }),
      });
    } catch {
      // Keep UI responsive even if the API is temporarily offline.
    }
    activeReminder = null;
    hideReminderPage();
    loadTodayEvents();
  }

  function handleWsMessage(data) {
    if (lastMsgAt) lastMsgAt.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    if (data.kind === "state" && data.serverNow) {
      serverOffsetMs = new Date(data.serverNow).getTime() - Date.now();
      tickClock();
      loadTodayEvents();
    } else if (data.kind === "devState") {
      const deviceId = data.deviceId || data.devId;
      if (deviceId && deviceId !== "pi") return;
      renderState(data.state);
    } else if (data.kind === "reminderSound") {
      playReminderSound();
      loadTodayEvents();
    } else if (data.kind === "reminder") {
      showReminderPage(data.title, data.content, data.evtId);
    }
  }

  function connectWs() {
    if (ws && [WebSocket.OPEN, WebSocket.CONNECTING].includes(ws.readyState)) return;
    ws = new WebSocket(wsUrl);
    ws.onopen = () => setWsConnected(true);
    ws.onmessage = (event) => {
      try {
        handleWsMessage(JSON.parse(event.data));
      } catch {
        showReminderPage("消息", event.data, null);
      }
    };
    ws.onclose = () => {
      setWsConnected(false);
      clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(connectWs, 1800);
    };
    ws.onerror = () => setWsConnected(false);
  }

  reminderDoneEl?.addEventListener("click", () => submitReminderAction("done"));
  reminderSnoozeEl?.addEventListener("click", () => submitReminderAction("snooze10"));
  document.body.addEventListener("pointerdown", () => getAudioCtx()?.resume?.(), { once: true });
  setInterval(tickClock, 1000);
  setInterval(loadTodayEvents, 30000);
  tickClock();
  renderState("unknown");
  renderSchedule([]);
  loadTodayEvents();
  connectWs();
})();
