import { describe, expect, it } from "vitest";

import { getEventPrimaryTime, type SmartCoreEvent } from "@/types/event";

const base = {
  evtId: "evt-1",
  title: "Example",
  stat: "todo" as const,
  prio: "mid" as const,
  createdAt: "2026-07-11T10:00:00+08:00",
  updatedAt: "2026-07-11T10:00:00+08:00",
};

describe("getEventPrimaryTime", () => {
  it.each<SmartCoreEvent>([
    { ...base, evtType: "plan", stTime: "2026-07-12T10:00:00+08:00", durationMin: 30 },
    { ...base, evtType: "remind", triggerTime: "2026-07-12T11:00:00+08:00", standalone: true },
    { ...base, evtType: "ddl", endTime: "2026-07-12T12:00:00+08:00", hardDdl: true, plans: [] },
  ])("returns the primary time for $evtType", (event) => {
    expect(getEventPrimaryTime(event)).toMatch(/^2026-07-12T/);
  });
});
