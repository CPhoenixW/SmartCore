import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import EventCard from "@/components/events/EventCard.vue";
import { i18n } from "@/locales";
import type { EventType, SmartCoreEvent } from "@/types/event";

function eventOfType(evtType: EventType): SmartCoreEvent {
  const base = {
    evtId: `event-${evtType}`,
    title: evtType,
    evtType,
    stat: "todo" as const,
    prio: "mid" as const,
  };
  if (evtType === "plan") {
    return { ...base, evtType, stTime: "2026-07-20T09:00:00+08:00", durationMin: 30 };
  }
  if (evtType === "remind") {
    return { ...base, evtType, triggerTime: "2026-07-20T09:00:00+08:00" };
  }
  if (evtType === "ddl") {
    return { ...base, evtType, endTime: "2026-07-20T09:00:00+08:00", hardDdl: false, plans: [], ddlReminders: [] };
  }
  return {
    ...base,
    evtType,
    courseName: "Course",
    weekDay: 1,
    startWeek: 1,
    endWeek: 1,
    weekMode: "all",
    stTime: "09:00",
    endTime: "10:00",
  };
}

describe("EventCard type colors", () => {
  it.each(["plan", "remind", "ddl", "course"] as EventType[])(
    "adds the shared %s type class",
    (evtType) => {
      const wrapper = mount(EventCard, {
        props: { event: eventOfType(evtType) },
        global: { plugins: [i18n] },
      });

      expect(wrapper.get("button").classes()).toContain(`event-card--type-${evtType}`);
    },
  );
});
