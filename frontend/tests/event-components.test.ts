import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import DdlPlanEditor from "@/components/events/DdlPlanEditor.vue";
import EventCard from "@/components/events/EventCard.vue";
import EventPreviewCard from "@/components/events/EventPreviewCard.vue";
import EventStatusToggle from "@/components/events/EventStatusToggle.vue";
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
    return {
      ...base,
      evtType,
      stTime: "2026-07-20T09:00:00+08:00",
      durationMin: 30,
    };
  }
  if (evtType === "remind") {
    return {
      ...base,
      evtType,
      triggerTime: "2026-07-20T09:00:00+08:00",
    };
  }
  if (evtType === "ddl") {
    return {
      ...base,
      evtType,
      endTime: "2026-07-20T09:00:00+08:00",
      hardDdl: false,
      plans: [],
      ddlReminders: [],
    };
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

describe("event components", () => {
  it("adds and removes manual DDL plans", async () => {
    const wrapper = mount(DdlPlanEditor, {
      props: { modelValue: [] },
      global: { mocks: { $t: (key: string) => key } },
    });
    await wrapper.get("button.button--ghost").trigger("click");
    expect(wrapper.emitted("update:modelValue")).toBeTruthy();
  });

  it.each(["plan", "remind", "ddl", "course"] as EventType[])(
    "adds the shared %s type class",
    (evtType) => {
      const wrapper = mount(EventCard, {
        props: { event: eventOfType(evtType) },
        global: { plugins: [i18n] },
      });

      expect(wrapper.get("button").classes()).toContain(
        `event-card--type-${evtType}`,
      );
    },
  );

  it("emits preview on click and edit on double click", async () => {
    const event = eventOfType("plan");
    const wrapper = mount(EventCard, {
      props: { event },
      global: { plugins: [i18n] },
    });

    await wrapper.get("button").trigger("click");
    await wrapper.get("button").trigger("dblclick");

    expect(wrapper.emitted("select")).toEqual([[event]]);
    expect(wrapper.emitted("edit")).toEqual([[event]]);
  });

  it("uses the shared detail preview structure", () => {
    const wrapper = mount(EventPreviewCard, {
      props: {
        type: "plan",
        title: "Shared preview",
        description: "The same content hierarchy as an idea.",
        time: "2026-07-20T09:00:00+08:00",
      },
      global: { plugins: [i18n] },
    });

    expect(wrapper.find(".detail-preview").exists()).toBe(true);
    expect(wrapper.find(".idea-detail-header").exists()).toBe(true);
    expect(wrapper.find(".idea-detail-copy").exists()).toBe(true);
  });

  it("renders todo unchecked and emits done when checked", async () => {
    const wrapper = mount(EventStatusToggle, {
      props: {
        status: "todo",
        markDoneLabel: "Mark done",
        markTodoLabel: "Mark todo",
      },
    });
    const checkbox = wrapper.get("input[type='checkbox']");

    expect((checkbox.element as HTMLInputElement).checked).toBe(false);
    await checkbox.setValue(true);
    expect(wrapper.emitted("change")).toEqual([["done"]]);
  });

  it("renders done checked and emits todo when unchecked", async () => {
    const wrapper = mount(EventStatusToggle, {
      props: {
        status: "done",
        markDoneLabel: "Mark done",
        markTodoLabel: "Mark todo",
      },
    });
    const checkbox = wrapper.get("input[type='checkbox']");

    expect((checkbox.element as HTMLInputElement).checked).toBe(true);
    await checkbox.setValue(false);
    expect(wrapper.emitted("change")).toEqual([["todo"]]);
  });
});
