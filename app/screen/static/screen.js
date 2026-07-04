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
  const latestReminderListEl = document.getElementById("latestReminderList");
  const todayEvtListEl = document.getElementById("todayEvtList");
  const expiredReminderListEl = document.getElementById("expiredReminderList");
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
  const expiredReminders = [];

  function setWsConnected(connected) {
    wsStatusEl.classList.toggle("connected", connected);
    wsStatusText.textContent = connected ? "已连接" : "离线";
  }

  function formatEnglishDate(now) {
    const weekday = now.toLocaleDateString("en-US", { weekday: "long" });
    const month = now.toLocaleDateString("en-US", { month: "long" });
    return `${weekday} ${month} ${now.getDate()} ${now.getFullYear()}`;
  }

  function formatDate(now) {
    return formatEnglishDate(now);
  }

  function tickClock() {
    const now = new Date(Date.now() + serverOffsetMs);
    const h = String(now.getHours()).padStart(2, "0");
    const m = String(now.getMinutes()).padStart(2, "0");
    clockHoursEl.textContent = h;
    clockMinsEl.textContent = m;
    clockSepEl.classList.toggle("blink-off", now.getSeconds() % 2 === 1);
    clockDateEl.textContent = formatDate(now);
    clockDateEl.lang = "en";
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
    shellEl.dataset.mode = mode;
    shellEl.classList.toggle("mode-working", working);
    shellEl.classList.toggle("mode-away", !working);
    if (stateRowEl) stateRowEl.hidden = !working;
    if (changed) tickClock();
  }

  function renderState(state) {
    const next = state || "unknown";
    stateEl.textContent = next;
    stateEl.className = next;
    if (stateCaptionEl) stateCaptionEl.textContent = STATE_CAPTIONS[next] || next;
    applyLayoutMode(next);
  }

  function getEvtDateValue(evt) {
    return evt.evtType === "life" ? evt.dueAt : evt.evtType === "ddl" ? evt.ddlAt : evt.classDate;
  }

  function isToday(dt) {
    const now = new Date(Date.now() + serverOffsetMs);
    return dt.getFullYear() === now.getFullYear()
      && dt.getMonth() === now.getMonth()
      && dt.getDate() === now.getDate();
  }

  function fmtEvtTime(evt) {
    const raw = getEvtDateValue(evt);
    if (!raw) return "--:--";
    const dt = new Date(raw);
    if (Number.isNaN(dt.getTime())) return String(raw).slice(0, 10);
    return dt.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  }

  function evtTypeLabel(evt) {
    return { life: "事项", ddl: "截止", course: "课程" }[evt.evtType] || evt.evtType || "事件";
  }

  function getTodayEvents(events) {
    return events
      .filter((evt) => evt.stat === "todo")
      .filter((evt) => {
        const raw = getEvtDateValue(evt);
        if (!raw) return false;
        const dt = new Date(raw);
        return !Number.isNaN(dt.getTime()) && isToday(dt);
      })
      .sort((a, b) => new Date(getEvtDateValue(a)).getTime() - new Date(getEvtDateValue(b)).getTime());
  }

  function renderLatestReminder() {
    latestReminderListEl.innerHTML = "";
    if (!activeReminder) {
      latestReminderListEl.classList.add("empty");
      latestReminderListEl.textContent = "No active reminder";
      return;
    }
    latestReminderListEl.classList.remove("empty");
    const card = document.createElement("article");
    card.className = "today-primary";
    card.innerHTML = '<div class="today-time"></div><h2></h2><p></p>';
    card.querySelector(".today-time").textContent = activeReminder.content || fmtEvtTime(activeReminder);
    card.querySelector("h2").textContent = activeReminder.title || "未命名提醒";
    card.querySelector("p").textContent = activeReminder.evtId ? `事件 ${activeReminder.evtId.slice(0, 8)}` : "等待确认";
    latestReminderListEl.appendChild(card);
  }

  function renderExpiredReminders() {
    expiredReminderListEl.innerHTML = "";
    if (!expiredReminders.length) {
      expiredReminderListEl.classList.add("empty");
      expiredReminderListEl.textContent = "No expired reminders";
      return;
    }
    expiredReminderListEl.classList.remove("empty");
    expiredReminders.forEach((item) => {
      const row = document.createElement("article");
      row.className = "expired-reminder";
      row.innerHTML = "<strong></strong><span></span>";
      row.querySelector("strong").textContent = item.title || "未命名提醒";
      row.querySelector("span").textContent = item.content || "";
      expiredReminderListEl.appendChild(row);
    });
  }

  function renderTodayEvents(events) {
    const todayEvents = getTodayEvents(events || []);
    const activeEvtId = activeReminder?.evtId;
    const filtered = activeEvtId
      ? todayEvents.filter((evt) => evt.evtId !== activeEvtId)
      : todayEvents;
    todayEvtListEl.innerHTML = "";
    todayEvtListEl.classList.toggle("empty", filtered.length === 0);
    if (!filtered.length) {
      todayEvtListEl.textContent = "No events today";
      return;
    }
    filtered.forEach((evt) => {
      const card = document.createElement("article");
      card.className = "today-compact";
      card.innerHTML = '<span class="today-chip"></span><strong></strong>';
      card.querySelector(".today-chip").textContent = `${evtTypeLabel(evt)} ${fmtEvtTime(evt)}`;
      card.querySelector("strong").textContent = evt.title || "未命名事件";
      todayEvtListEl.appendChild(card);
    });
  }

  async function loadTodayEvents() {
    try {
      const resp = await fetch("/api/evt");
      const data = await resp.json();
      renderTodayEvents(data.data || []);
    } catch {
      todayEvtListEl.textContent = "Events offline";
      todayEvtListEl.classList.add("empty");
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
    reminderPageEl.classList.remove("show");
    reminderPageEl.setAttribute("aria-hidden", "true");
    clearExpireTimer();
  }

  function showReminderPage(title, content, evtId) {
    activeReminder = { title, content, evtId: evtId || null };
    reminderPageTitleEl.textContent = title || "提醒";
    reminderPageContentEl.textContent = content || "";
    reminderPageEl.classList.add("show");
    reminderPageEl.setAttribute("aria-hidden", "false");
    renderLatestReminder();
    loadTodayEvents();
    playReminderSound();
    clearExpireTimer();
    expireTimer = setTimeout(expireActiveReminder, 60000);
  }

  function expireActiveReminder() {
    if (!activeReminder) return;
    expiredReminders.unshift({ ...activeReminder });
    activeReminder = null;
    hideReminderPage();
    renderLatestReminder();
    renderExpiredReminders();
    loadTodayEvents();
  }

  async function submitReminderAction(action) {
    if (!activeReminder?.evtId) {
      hideReminderPage();
      activeReminder = null;
      renderLatestReminder();
      return;
    }
    try {
      await fetch("/api/reminder/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          evtId: activeReminder.evtId,
          action,
        }),
      });
    } catch {
      // Keep UI responsive even if the API is temporarily offline.
    }
    activeReminder = null;
    hideReminderPage();
    renderLatestReminder();
    loadTodayEvents();
  }

  function handleWsMessage(data) {
    lastMsgAt.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    if (data.kind === "state" && data.serverNow) {
      serverOffsetMs = new Date(data.serverNow).getTime() - Date.now();
      tickClock();
      loadTodayEvents();
    } else if (data.kind === "devState") {
      if (data.devId && data.devId !== "pi") return;
      renderState(data.state);
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
  setInterval(loadTodayEvents, 60000);
  tickClock();
  renderState("unknown");
  renderLatestReminder();
  renderExpiredReminders();
  loadTodayEvents();
  connectWs();
  window.handleWsMessage = handleWsMessage;
  window.expireActiveReminder = expireActiveReminder;
  window.submitReminderAction = submitReminderAction;
  window.showReminderPage = showReminderPage;
  window.renderTodayEvents = renderTodayEvents;
  window.loadTodayEvents = loadTodayEvents;
})();
