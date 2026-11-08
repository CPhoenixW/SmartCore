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

  it("keeps live progress inside the conversation while DSH is working", async () => {
    let resolveStream: ((value: { sessionId: string; response: string }) => void) | undefined;
    streamMock.mockImplementation((_text: string, _conversationId: string, onEvent: (event: object) => void) => {
      onEvent({ type: "status", phase: "thinking", message: "我先理解一下你的请求…" });
      onEvent({ type: "tool", state: "start", name: "evtQuery", message: "正在查询你的安排…" });
      onEvent({ type: "message", text: "我来帮你查一下。", mode: "new" });
      return new Promise<{ sessionId: string; response: string }>((resolve) => { resolveStream = resolve; });
    });
    const wrapper = mount(AssistantView, { global: { plugins: [i18n] } });
    await flushPromises();

    await wrapper.get("textarea").setValue("我今天有什么安排？");
    void wrapper.get(".assistant-composer").trigger("submit");
    await flushPromises();

    expect(wrapper.find(".assistant-progress").exists()).toBe(true);
    expect(wrapper.find(".assistant-progress").text()).toContain("正在查询你的安排");
    expect(wrapper.find(".assistant-message--streaming").text()).toContain("我来帮你查一下");
    expect(wrapper.find(".assistant-message__cursor").exists()).toBe(false);
    expect(wrapper.find(".assistant-status").exists()).toBe(false);
    expect(wrapper.get("textarea").attributes("disabled")).toBeUndefined();

    resolveStream?.({ sessionId: "pwa-test", response: "已创建计划" });
    await flushPromises();
    expect(wrapper.find(".assistant-progress").exists()).toBe(false);
    expect(wrapper.text()).toContain("已创建计划");
  });

  it("renders assistant markdown instead of plain paragraphs", async () => {
    readMock.mockResolvedValueOnce({
      conversationId: "pwa-test",
      title: "Markdown",
      stat: "active",
      createdAt: "2026-07-31T10:00:00+08:00",
      updatedAt: "2026-07-31T10:00:00+08:00",
      lastMessageAt: "2026-07-31T10:00:00+08:00",
      messages: [{
        messageId: "assistant-md",
        conversationId: "pwa-test",
        role: "assistant",
        text: "## 安排\n- 复习\n- 运动",
        stat: "complete",
        createdAt: "2026-07-31T10:00:00+08:00",
      }],
    });
    const wrapper = mount(AssistantView, { global: { plugins: [i18n] } });
    await flushPromises();
    expect(wrapper.find(".markdown-content h2").text()).toContain("安排");
    expect(wrapper.findAll(".markdown-content li")).toHaveLength(2);
  });

  it("renders reminder notifications as compact human-readable cards", async () => {
    readMock.mockResolvedValueOnce({
      conversationId: "pwa-test",
      title: "提醒",
      stat: "active",
      createdAt: "2026-07-31T10:00:00+08:00",
      updatedAt: "2026-07-31T10:00:00+08:00",
      lastMessageAt: "2026-07-31T10:00:00+08:00",
      messages: [{
        messageId: "assistant-reminder",
        conversationId: "pwa-test",
        role: "assistant",
        text: "🔔 计算机网络作业 · 开始前 10 分钟\n\n计划将在 10 分钟后开始：2026-11-08T14:00:00+08:00",
        stat: "complete",
        createdAt: "2026-07-31T10:00:00+08:00",
      }],
    });
    const wrapper = mount(AssistantView, { global: { plugins: [i18n] } });
    await flushPromises();

    expect(wrapper.find(".assistant-identity").text()).toContain("SmartCore 助手");
    expect(wrapper.find(".assistant-date-divider").exists()).toBe(true);
    expect(wrapper.find(".assistant-capabilities").exists()).toBe(false);
    expect(wrapper.find(".assistant-reminder-card").exists()).toBe(true);
    expect(wrapper.find(".assistant-reminder-card").text()).not.toContain("2026-11-08T14:00:00+08:00");
    expect(wrapper.find(".assistant-reminder-card").text()).toContain("计划开始");
  });

  it("keeps an empty conversation quiet and focused", async () => {
    readMock.mockResolvedValueOnce({ conversationId: "pwa-test", title: "SmartCore 助手", stat: "active", createdAt: "2026-07-31T10:00:00+08:00", updatedAt: "2026-07-31T10:00:00+08:00", lastMessageAt: null, messages: [] });
    const wrapper = mount(AssistantView, { global: { plugins: [i18n] } });
    await flushPromises();

    expect(wrapper.find(".assistant-empty").text()).toContain("从一句话开始");
    expect(wrapper.find(".assistant-quick-prompts").exists()).toBe(false);
  });
});
