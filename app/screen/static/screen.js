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
  const reminderEl = document.getElementById("reminderArea");
  const wsStatusEl = document.getElementById("wsStatus");
  const wsStatusText = document.getElementById("wsStatusText");
  const lastMsgAt = document.getElementById("lastMsgAt");
  const heartbeat = document.getElementById("heartbeat");
  let ws = null;
  let reconnectTimer = null;
  let serverOffsetMs = 0;
  let hasReminders = false;
  let currentMode = "away";

  function setWsConnected(connected) {
    wsStatusEl.classList.toggle("connected", connected);
    wsStatusText.textContent = connected ? "已连接" : "离线";
  }

  function formatDate(now) {
    if (currentMode === "away") {
      const weekday = now.toLocaleDateString("en-US", { weekday: "long" });
      const month = now.toLocaleDateString("en-US", { month: "long" });
      return `${weekday} ${month} ${now.getDate()} ${now.getFullYear()}`;
    }
    const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
    return `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 ${weekdays[now.getDay()]}`;
  }

  function tickClock() {
    const now = new Date(Date.now() + serverOffsetMs);
    const h = String(now.getHours()).padStart(2, "0");
    const m = String(now.getMinutes()).padStart(2, "0");
    clockHoursEl.textContent = h;
    clockMinsEl.textContent = m;
    clockSepEl.classList.toggle("blink-off", now.getSeconds() % 2 === 1);
    clockDateEl.textContent = formatDate(now);
    clockDateEl.lang = currentMode === "away" ? "en" : "zh-CN";
    heartbeat.textContent = now.toLocaleTimeString("zh-CN", { hour12: false });
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

    if (stateRowEl) {
      stateRowEl.hidden = !working;
    }
    if (changed) {
      tickClock();
    }
  }

  function renderState(state) {
    const next = state || "unknown";
    stateEl.textContent = next;
    stateEl.className = next;
    if (stateCaptionEl) {
      stateCaptionEl.textContent = STATE_CAPTIONS[next] || next;
    }
    applyLayoutMode(next);
  }

  function addReminder(title, content) {
    if (currentMode !== "working") return;
    if (!hasReminders) {
      reminderEl.innerHTML = "";
      reminderEl.classList.remove("empty");
      hasReminders = true;
    }
    const card = document.createElement("div");
    card.className = "reminder-card";
    card.innerHTML = '<div class="rem-title"></div><div class="rem-content"></div>';
    card.querySelector(".rem-title").textContent = title || "提醒";
    card.querySelector(".rem-content").textContent = content || "";
    reminderEl.prepend(card);
    while (reminderEl.children.length > 8) reminderEl.removeChild(reminderEl.lastChild);
  }

  function handleWsMessage(data) {
    lastMsgAt.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    if (data.kind === "state" && data.serverNow) {
      serverOffsetMs = new Date(data.serverNow).getTime() - Date.now();
      tickClock();
    } else if (data.kind === "devState") {
      if (data.devId && data.devId !== "pi") return;
      renderState(data.state);
    } else if (data.kind === "reminder") {
      addReminder(data.title, data.content);
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
        addReminder("消息", event.data);
      }
    };
    ws.onclose = () => {
      setWsConnected(false);
      clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(connectWs, 1800);
    };
    ws.onerror = () => setWsConnected(false);
  }

  setInterval(tickClock, 1000);
  tickClock();
  renderState("unknown");
  connectWs();
  window.handleWsMessage = handleWsMessage;
})();
