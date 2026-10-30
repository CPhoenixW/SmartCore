import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AssistantView from "@/views/AssistantView.vue";
import { i18n } from "@/locales";

const { streamMock } = vi.hoisted(() => ({ streamMock: vi.fn() }));

vi.mock("@/api/assistant", () => ({
  assistantApi: { stream: streamMock },
}));

describe("AssistantView", () => {
  beforeEach(() => streamMock.mockReset());

  it("sends a message and renders the assistant response", async () => {
    streamMock.mockResolvedValue({ sessionId: "pwa-test", response: "已创建计划" });
    const wrapper = mount(AssistantView, { global: { plugins: [i18n] } });
    const textarea = wrapper.get("textarea");

    await textarea.setValue("明天上午安排复习");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(streamMock).toHaveBeenCalledWith("明天上午安排复习", expect.any(String), expect.any(Function));
    expect(wrapper.text()).toContain("明天上午安排复习");
    expect(wrapper.text()).toContain("已创建计划");
  });
});
