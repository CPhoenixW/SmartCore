import { describe, expect, it } from "vitest";
import { defaultDdlPlans, getEventPrimaryTime } from "@/utils/date";
import { sortEvents } from "@/utils/event";
import type { SmartCoreEvent } from "@/types/event";

describe("event utilities", () => {
  it("returns the discriminated primary time", () => {
    expect(getEventPrimaryTime({ evtId: "1", title: "x", evtType: "remind", stat: "todo", prio: "mid", triggerTime: "2026-01-01T00:00:00Z" })).toBe("2026-01-01T00:00:00Z");
  });
  it("creates one-day and one-hour DDL plans", () => {
    const plans = defaultDdlPlans("2026-07-12T12:00:00Z");
    expect(plans.map((plan) => plan.planRole)).toEqual(["one_day_before", "one_hour_before"]);
    expect(new Date(plans[0]!.stTime).getTime()).toBe(new Date("2026-07-11T12:00:00Z").getTime());
  });
  it("keeps completed events and sorts todo first", () => {
    const events: SmartCoreEvent[] = [
      { evtId: "2", title: "done", evtType: "plan", stat: "done", prio: "mid", stTime: "2026-01-01T09:00:00Z", durationMin: 30 },
      { evtId: "1", title: "todo", evtType: "plan", stat: "todo", prio: "mid", stTime: "2026-01-01T10:00:00Z", durationMin: 30 },
    ];
    expect(sortEvents(events).map((item) => item.evtId)).toEqual(["1", "2"]);
  });
});
