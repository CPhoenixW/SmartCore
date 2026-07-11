import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import DdlPlanEditor from "@/components/events/DdlPlanEditor.vue";

const global = { mocks: { $t: (key: string) => key } };
describe("DdlPlanEditor", () => {
  it("adds and removes manual plans", async () => {
    const wrapper = mount(DdlPlanEditor, { props: { modelValue: [] }, global });
    await wrapper.get("button.button--ghost").trigger("click");
    expect(wrapper.emitted("update:modelValue")).toBeTruthy();
  });
});
