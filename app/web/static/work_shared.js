export function ensureDeviceNav(active = false) {
  const nav = document.querySelector(".work-nav");
  if (!nav || nav.querySelector('[href="/work/device"]')) return;
  const link = document.createElement("a");
  link.className = `nav-link${active ? " active" : ""}`;
  link.href = "/work/device";
  link.innerHTML = '<span class="nav-ico">◉</span>设备';
  const settings = nav.querySelector('[href="/work/settings"]');
  nav.insertBefore(link, settings || null);
}

export function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

export function deviceStateView(row, staleSeconds = 35) {
  if (!row) {
    return {
      state: "offline",
      label: "离线",
      stale: true,
      seenAt: null,
      confidence: null,
      present: false,
      persons: [],
      meta: {},
    };
  }
  const seen = row.seenAt ? new Date(row.seenAt) : null;
  const stale = !seen || Number.isNaN(seen.getTime()) || Date.now() - seen.getTime() > staleSeconds * 1000;
  const state = stale ? "offline" : (row.state || "unknown");
  const labels = { working: "工作中", away: "离开", offline: "离线", unknown: "未知" };
  const meta = row.meta && typeof row.meta === "object" ? row.meta : {};
  return {
    state,
    label: labels[state] || state,
    stale,
    seenAt: row.seenAt || null,
    confidence: row.confidence,
    present: Boolean(meta.present),
    persons: Array.isArray(meta.persons) ? meta.persons : [],
    meta,
  };
}
