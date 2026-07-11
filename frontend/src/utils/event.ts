import type { EventStatus, Priority, SmartCoreEvent } from "@/types/event";
import { getEventPrimaryTime } from "./date";

const statusRank: Record<EventStatus, number> = { todo: 0, done: 1, cancelled: 2 };
const priorityRank: Record<Priority, number> = { high: 0, mid: 1, low: 2 };

export function sortEvents(events: SmartCoreEvent[]): SmartCoreEvent[] {
  return [...events].sort((a, b) =>
    statusRank[a.stat] - statusRank[b.stat] ||
    new Date(getEventPrimaryTime(a)).getTime() - new Date(getEventPrimaryTime(b)).getTime() ||
    priorityRank[a.prio] - priorityRank[b.prio],
  );
}

export function eventTypeLabelKey(event: SmartCoreEvent): string {
  return `event.type.${event.evtType}`;
}
