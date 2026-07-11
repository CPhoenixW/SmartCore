import type { DeviceMeta, DeviceState, DeviceStateView } from "@/types/device";

export function parseDeviceMeta(value: DeviceState["meta"]): DeviceMeta {
  if (value && typeof value === "object") return value;
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value) as unknown;
      return parsed && typeof parsed === "object" ? parsed as DeviceMeta : {};
    } catch {
      return {};
    }
  }
  return {};
}

export function deviceStateView(row: DeviceState | null | undefined, staleSeconds = 35): DeviceStateView {
  if (!row) return { state: "offline", label: "离线", stale: true, seenAt: null, confidence: null, present: false, persons: [], meta: {} };
  const seen = row.seenAt ? new Date(row.seenAt) : null;
  const stale = !seen || Number.isNaN(seen.getTime()) || Date.now() - seen.getTime() > staleSeconds * 1000;
  const state = stale ? "offline" : (row.state || "unknown");
  const labels: Record<string, string> = { working: "工作中", away: "离开", offline: "离线", unknown: "未知" };
  const meta = parseDeviceMeta(row.meta);
  return {
    state,
    label: labels[state] ?? state,
    stale,
    seenAt: row.seenAt || null,
    confidence: row.confidence == null ? null : Number(row.confidence),
    present: Boolean(meta.present),
    persons: Array.isArray(meta.persons) ? meta.persons : [],
    meta,
  };
}

export function devicePersonNames(view: DeviceStateView): string[] {
  return view.persons.map((person) => String(person.name ?? person.personId ?? "")).filter(Boolean);
}
