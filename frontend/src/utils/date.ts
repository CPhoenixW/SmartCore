import type { DdlPlan, SmartCoreEvent } from "@/types/event";

export function todayKey(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

export function getEventPrimaryTime(event: SmartCoreEvent): string {
  switch (event.evtType) {
    case "plan": return event.stTime;
    case "remind": return event.triggerTime;
    case "ddl": return event.endTime;
    case "course": return event.stTime;
  }
}

export function formatDateTime(value?: string | null, locale = "zh-CN"): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { month: "2-digit", day: "2-digit", weekday: "short", hour: "2-digit", minute: "2-digit" }).format(date);
}

export function toLocalInput(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16);
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 16);
}

export function localInputToIso(value: string): string {
  return value ? new Date(value).toISOString() : "";
}

export function defaultDdlPlans(endTime: string): DdlPlan[] {
  const end = new Date(endTime);
  if (Number.isNaN(end.getTime())) return [];
  return [
    { planRole: "one_day_before", stTime: new Date(end.getTime() - 86_400_000).toISOString(), durationMin: 30, sortOrder: 0 },
    { planRole: "one_hour_before", stTime: new Date(end.getTime() - 3_600_000).toISOString(), durationMin: 30, sortOrder: 1 },
  ];
}

export function addDays(date: string, days: number): string {
  const next = new Date(`${date}T12:00:00`);
  next.setDate(next.getDate() + days);
  return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}-${String(next.getDate()).padStart(2, "0")}`;
}
