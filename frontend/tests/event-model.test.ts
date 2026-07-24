import { reactive } from "vue";
import { describe, expect, it } from "vitest";
import { defaultDdlPlans, getEventPrimaryTime } from "@/utils/date";
import { sortEvents } from "@/utils/event";
import { cloneDdlRelations } from "@/utils/eventEditor";
import type { DdlEvent, SmartCoreEvent } from "@/types/event";

describe("event model utilities", () => {
  it("returns the discriminated primary time", () => {
    expect(
      getEventPrimaryTime({
        evtId: "1",
        title: "x",
        evtType: "remind",
        stat: "todo",
        prio: "mid",
        triggerTime: "2026-01-01T00:00:00Z",
      }),
    ).toBe("2026-01-01T00:00:00Z");
  });

  it("creates one-day and one-hour DDL plans", () => {
    const plans = defaultDdlPlans("2026-07-12T12:00:00Z");
    expect(plans.map((plan) => plan.planRole)).toEqual([
      "one_day_before",
      "one_hour_before",
    ]);
    expect(new Date(plans[0]!.stTime).getTime()).toBe(
      new Date("2026-07-11T12:00:00Z").getTime(),
    );
  });

  it("keeps completed events and sorts todo first", () => {
    const events: SmartCoreEvent[] = [
      {
        evtId: "2",
        title: "done",
        evtType: "plan",
        stat: "done",
        prio: "mid",
        stTime: "2026-01-01T09:00:00Z",
        durationMin: 30,
      },
      {
        evtId: "1",
        title: "todo",
        evtType: "plan",
        stat: "todo",
        prio: "mid",
        stTime: "2026-01-01T10:00:00Z",
        durationMin: 30,
      },
    ];
    expect(sortEvents(events).map((item) => item.evtId)).toEqual(["1", "2"]);
  });

  it("clones complete relations from a Vue reactive event", () => {
    const source = reactive<DdlEvent>({
      evtId: "ddl-1",
      evtType: "ddl",
      title: "Submit report",
      stat: "todo",
      prio: "high",
      endTime: "2026-07-20T18:00:00+08:00",
      hardDdl: true,
      plans: [
        {
          planEvtId: "plan-1",
          planRole: "manual",
          stTime: "2026-07-20T10:00:00+08:00",
          durationMin: 60,
          enabled: true,
          sortOrder: 0,
        },
      ],
      ddlReminders: [
        {
          remindEvtId: "reminder-1",
          title: "Submit soon",
          triggerTime: "2026-07-20T16:00:00+08:00",
          enabled: true,
        },
      ],
    });

    const result = cloneDdlRelations(source);

    expect(result.plans).toEqual(source.plans);
    expect(result.ddlReminders).toEqual(source.ddlReminders);
    expect(result.plans[0]).not.toBe(source.plans[0]);
    expect(result.ddlReminders[0]).not.toBe(source.ddlReminders[0]);
  });
});
