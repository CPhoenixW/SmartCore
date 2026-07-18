import { reactive } from "vue";
import { describe, expect, it } from "vitest";
import { cloneDdlRelations } from "@/utils/eventEditor";
import type { DdlEvent } from "@/types/event";

describe("DDL editor relations", () => {
  it("clones complete relations from a Vue reactive event", () => {
    const source = reactive<DdlEvent>({
      evtId: "ddl-1",
      evtType: "ddl",
      title: "Submit report",
      stat: "todo",
      prio: "high",
      endTime: "2026-07-20T18:00:00+08:00",
      hardDdl: true,
      plans: [{
        planEvtId: "plan-1",
        planRole: "manual",
        stTime: "2026-07-20T10:00:00+08:00",
        durationMin: 60,
        enabled: true,
        sortOrder: 0,
      }],
      ddlReminders: [{
        remindEvtId: "reminder-1",
        title: "Submit soon",
        triggerTime: "2026-07-20T16:00:00+08:00",
        enabled: true,
      }],
    });

    const result = cloneDdlRelations(source);

    expect(result.plans).toEqual(source.plans);
    expect(result.ddlReminders).toEqual(source.ddlReminders);
    expect(result.plans[0]).not.toBe(source.plans[0]);
    expect(result.ddlReminders[0]).not.toBe(source.ddlReminders[0]);
  });
});
