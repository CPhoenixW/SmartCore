import type { ComputerState, ComputerTimelinePoint } from "@/types/computer";

const objectiveStates: Exclude<ComputerState, "offline">[] = ["active", "idle", "locked", "sleeping", "paused"];

export function dominantComputerState(point: ComputerTimelinePoint): Exclude<ComputerState, "offline"> {
  return objectiveStates.reduce((best, state) => point.states[state] > point.states[best] ? state : best, "active");
}

export function durationLabel(seconds: number, locale = "en-US"): string {
  const totalMinutes = Math.round(Math.max(0, seconds) / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (locale.startsWith("zh")) {
    if (hours && minutes) return `${hours}小时 ${minutes}分钟`;
    if (hours) return `${hours}小时`;
    return `${minutes}分钟`;
  }
  if (hours && minutes) return `${hours}h ${minutes}m`;
  if (hours) return `${hours}h`;
  return `${minutes}m`;
}

export function timelineTicks(windowStart: string, windowEnd: string, count = 5): string[] {
  const start = new Date(windowStart).getTime();
  const end = new Date(windowEnd).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || count < 2) return [];
  return Array.from({ length: count }, (_, index) => new Date(start + ((end - start) * index) / (count - 1)).toISOString());
}

export function timelinePosition(startAt: string, endAt: string, windowStart: string, windowEnd: string) {
  const start = new Date(startAt).getTime();
  const end = new Date(endAt).getTime();
  const rangeStart = new Date(windowStart).getTime();
  const rangeEnd = new Date(windowEnd).getTime();
  const width = Math.max(1, rangeEnd - rangeStart);
  const left = Math.max(0, Math.min(100, ((start - rangeStart) / width) * 100));
  const right = Math.max(left, Math.min(100, ((end - rangeStart) / width) * 100));
  return { left: `${left}%`, width: `${Math.max(0.2, right - left)}%` };
}
