import type { EventStatus, Priority, SmartCoreEvent } from "@/types/event";
import { getEventPrimaryTime, normalizeSearch } from "./date";

const statusRank: Record<EventStatus, number> = { todo: 0, done: 1, cancelled: 2 };
const priorityRank: Record<Priority, number> = { high: 0, mid: 1, low: 2 };

export function eventEndTime(event: SmartCoreEvent): number {
  const start = new Date(getEventPrimaryTime(event)).getTime();
  if (!Number.isFinite(start)) return Number.MAX_SAFE_INTEGER;
  return event.evtType === "plan" ? start + Math.max(1, event.durationMin) * 60_000 : start;
}

export function isOverdue(event: SmartCoreEvent, now = Date.now()): boolean {
  return event.stat === "todo" && event.evtType !== "course" && eventEndTime(event) < now;
}

export function sortEvents(events: SmartCoreEvent[]): SmartCoreEvent[] {
  return [...events].sort((a, b) => {
    const overdue = Number(isOverdue(b)) - Number(isOverdue(a));
    if (overdue) return overdue;
    const time = new Date(getEventPrimaryTime(a)).getTime() - new Date(getEventPrimaryTime(b)).getTime();
    if (Number.isFinite(time) && time !== 0) return time;
    return statusRank[a.stat] - statusRank[b.stat] || priorityRank[a.prio] - priorityRank[b.prio];
  });
}

export function eventSearchText(event: SmartCoreEvent): string {
  const values: unknown[] = [event.title, event.desc, event.evtType, event.prio, event.stat, getEventPrimaryTime(event)];
  if (event.evtType === "plan") values.push(event.courseName, event.occurrenceDate, event.generatedBy, event.planRole);
  if (event.evtType === "course") values.push(event.courseName, event.teacher, event.location, event.semesterStart, event.stDate, event.endDate, event.weekDay, event.weekMode, event.stTime, event.endTime);
  const instant = new Date(getEventPrimaryTime(event));
  if (!Number.isNaN(instant.getTime())) {
    const weekdayZh = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"][instant.getDay()];
    const hh = String(instant.getHours()).padStart(2, "0");
    const mm = String(instant.getMinutes()).padStart(2, "0");
    values.push(`${instant.getFullYear()}-${String(instant.getMonth() + 1).padStart(2, "0")}-${String(instant.getDate()).padStart(2, "0")}`, `${hh}:${mm}`, weekdayZh);
  }
  return normalizeSearch(values.filter((value) => value !== undefined && value !== null).join(" "));
}

export function matchesEventSearch(event: SmartCoreEvent, query: string): boolean {
  const normalized = normalizeSearch(query);
  return !normalized || eventSearchText(event).includes(normalized);
}
