import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AssistantView from "@/views/AssistantView.vue";
import { i18n } from "@/locales";

const { streamMock, listMock, readMock } = vi.hoisted(() => ({
  streamMock: vi.fn(),
  listMock: vi.fn(),
  readMock: vi.fn(),
}));

vi.mock("@/api/assistant", () => ({
  assistantApi: { stream: streamMock, list: listMock, read: readMock },
}));

describe("AssistantView", () => {
beforeEach(() => {
  streamMock.mockReset();
  listMock.mockReset().mockResolvedValue({ items: [{ conversationId: "pwa-test", title: "SmartCore 助手", stat: "active", createdAt: "2026-07-31T10:00:00+08:00", updatedAt: "2026-07-31T10:00:00+08:00", lastMessageAt: null }], query: "" });
  readMock.mockReset().mockResolvedValue({ conversationId: "pwa-test", title: "明天上午安排复习", stat: "active", createdAt: "2026-07-31T10:00:00+08:00", updatedAt: "2026-07-31T10:00:00+08:00", lastMessageAt: "2026-07-31T10:00:00+08:00", messages: [{ messageId: "assistant-1", conversationId: "pwa-test", role: "assistant", text: "已创建计划", stat: "complete", createdAt: "2026-07-31T10:00:00+08:00" }] });
});

  it("sends a message and renders the assistant response", async () => {
    streamMock.mockResolvedValue({ sessionId: "pwa-test", response: "已创建计划" });
    const wrapper = mount(AssistantView, { global: { plugins: [i18n] } });
    await flushPromises();
    const textarea = wrapper.get("textarea");

    await textarea.setValue("明天上午安排复习");
    await wrapper.get(".assistant-composer").trigger("submit");
    await flushPromises();

    expect(streamMock).toHaveBeenCalledWith("明天上午安排复习", expect.any(String), expect.any(Function), expect.any(String));
    expect(wrapper.text()).toContain("明天上午安排复习");
    expect(wrapper.text()).toContain("已创建计划");
  });
});
