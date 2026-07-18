import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import EventStatusToggle from "@/components/events/EventStatusToggle.vue";

describe("EventStatusToggle", () => {
  it("renders todo unchecked and emits done when checked", async () => {
    const wrapper = mount(EventStatusToggle, {
      props: { status: "todo", markDoneLabel: "Mark done", markTodoLabel: "Mark todo" },
    });
    const checkbox = wrapper.get("input[type='checkbox']");

    expect((checkbox.element as HTMLInputElement).checked).toBe(false);
    await checkbox.setValue(true);
    expect(wrapper.emitted("change")).toEqual([["done"]]);
  });

  it("renders done checked and emits todo when unchecked", async () => {
    const wrapper = mount(EventStatusToggle, {
      props: { status: "done", markDoneLabel: "Mark done", markTodoLabel: "Mark todo" },
    });
    const checkbox = wrapper.get("input[type='checkbox']");

    expect((checkbox.element as HTMLInputElement).checked).toBe(true);
    await checkbox.setValue(false);
    expect(wrapper.emitted("change")).toEqual([["todo"]]);
  });
});
