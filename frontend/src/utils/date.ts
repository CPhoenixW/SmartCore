import type { DdlPlan, SmartCoreEvent } from "@/types/event";

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

export function todayKey(): string {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function getEventPrimaryTime(event: SmartCoreEvent): string {
  switch (event.evtType) {
    case "plan": return event.stTime;
    case "remind": return event.triggerTime;
    case "ddl": return event.endTime;
    case "course": return event.nextOccurrence?.stTime ?? event.stDate ?? event.semesterStart ?? "";
  }
}

export function eventDateKey(event: SmartCoreEvent): string {
  const raw = getEventPrimaryTime(event);
  if (!raw) return todayKey();
  const date = new Date(raw.includes("T") ? raw : `${raw}T12:00:00`);
  if (Number.isNaN(date.getTime())) return raw.slice(0, 10) || todayKey();
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function formatDateTime(value?: string | null, locale = "zh-CN"): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.replace("T", " ");
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function toLocalInput(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function localInputToIso(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  const absolute = Math.abs(offset);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:00${sign}${pad(Math.floor(absolute / 60))}:${pad(absolute % 60)}`;
}

export function defaultDdlPlans(endTime: string): DdlPlan[] {
  const end = new Date(endTime);
  if (Number.isNaN(end.getTime())) return [];
  return [
    { planRole: "one_day_before", stTime: new Date(end.getTime() - 86_400_000).toISOString(), durationMin: 30, enabled: true, sortOrder: 0 },
    { planRole: "one_hour_before", stTime: new Date(end.getTime() - 3_600_000).toISOString(), durationMin: 30, enabled: true, sortOrder: 1 },
  ];
}

export function addDays(date: string, days: number): string {
  const next = new Date(`${date}T12:00:00`);
  next.setDate(next.getDate() + days);
  return `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}`;
}

export function normalizeSearch(value: string): string {
  let text = String(value || "").trim().toLowerCase().replace(/\//g, "-");
  text = text.replace(
    /(\d{1,2})点半/g,
    (_match: string, hour: string) => `${pad(Number(hour))}:30`,
  );
  text = text.replace(
    /(\d{1,2})点(?:(\d{1,2})分?)?/g,
    (_match: string, hour: string, minute?: string) =>
      `${pad(Number(hour))}:${pad(Number(minute || 0))}`,
  );
  return text;
}

export function extractDateQuery(value: string): string | null {
  const text = String(value || "");
  const match = text.match(/(20\d{2})[年\-/](\d{1,2})[月\-/](\d{1,2})日?/);
  if (!match) return null;
  const candidate = `${match[1]}-${pad(Number(match[2]))}-${pad(Number(match[3]))}`;
  const parsed = new Date(`${candidate}T12:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : candidate;
}
