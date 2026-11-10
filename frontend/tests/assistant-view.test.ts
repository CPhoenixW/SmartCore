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

    expect(streamMock).toHaveBeenCalledWith(
      "明天上午安排复习",
      expect.any(String),
      expect.any(Function),
      expect.any(String),
      expect.objectContaining({ signal: expect.anything() }),
    );
    expect(wrapper.text()).toContain("明天上午安排复习");
    expect(wrapper.text()).toContain("已创建计划");
  });

  it("opens at the newest messages and loads earlier history on demand", async () => {
    const history = Array.from({ length: 45 }, (_, index) => ({
      messageId: `history-${index}`,
      conversationId: "pwa-test",
      role: index % 2 ? "assistant" as const : "user" as const,
      text: `历史消息 ${index}`,
      stat: "complete" as const,
      createdAt: `2026-07-31T10:${String(index).padStart(2, "0")}:00+08:00`,
    }));
    readMock.mockResolvedValueOnce({
      conversationId: "pwa-test",
      title: "长对话",
      stat: "active",
      createdAt: "2026-07-31T10:00:00+08:00",
      updatedAt: "2026-07-31T10:44:00+08:00",
      lastMessageAt: "2026-07-31T10:44:00+08:00",
      messages: history,
    });
    const originalScrollHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollHeight");
    Object.defineProperty(HTMLElement.prototype, "scrollHeight", { configurable: true, get: () => 1200 });
    const wrapper = mount(AssistantView, { global: { plugins: [i18n] } });
    await flushPromises();

    const visible = wrapper.findAll(".assistant-message");
    expect(visible).toHaveLength(40);
    expect(wrapper.text()).toContain("历史消息 44");
    expect(wrapper.text()).not.toContain("历史消息 0");
    expect((wrapper.get(".assistant-messages").element as HTMLElement).scrollTop).toBe(1200);

    await wrapper.get(".assistant-history-load").trigger("click");
    await flushPromises();
    expect(wrapper.findAll(".assistant-message")).toHaveLength(45);
    expect(wrapper.text()).toContain("历史消息 0");
    expect(wrapper.find(".assistant-history-load").exists()).toBe(false);

    if (originalScrollHeight) Object.defineProperty(HTMLElement.prototype, "scrollHeight", originalScrollHeight);
    else delete (HTMLElement.prototype as unknown as Record<string, unknown>).scrollHeight;
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

  it("keeps drafting during generation and can stop the active stream", async () => {
    let signal: AbortSignal | undefined;
    streamMock.mockImplementation((_text: string, _conversationId: string, _onEvent: (event: object) => void, _clientMessageId: string, options?: { signal?: AbortSignal }) => {
      signal = options?.signal;
      return new Promise<never>((_resolve, reject) => {
        signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
      });
    });
    const wrapper = mount(AssistantView, { global: { plugins: [i18n] } });
    await flushPromises();

    const textarea = wrapper.get("textarea");
    await textarea.setValue("当前查询");
    void wrapper.get(".assistant-composer").trigger("submit");
    await flushPromises();

    expect(textarea.attributes("disabled")).toBeUndefined();
    expect(wrapper.find(".assistant-stop").exists()).toBe(true);
    await textarea.setValue("下一句");
    expect((textarea.element as HTMLTextAreaElement).value).toBe("下一句");
    expect(wrapper.find(".assistant-stop").exists()).toBe(false);
    expect(wrapper.get(".assistant-send").attributes("type")).toBe("submit");

    await textarea.setValue("");
    expect(wrapper.find(".assistant-stop").exists()).toBe(true);
    await wrapper.get(".assistant-stop").trigger("click");
    await new Promise((resolve) => setTimeout(resolve, 150));
    await flushPromises();

    expect(signal?.aborted).toBe(true);
    expect(wrapper.find(".assistant-stop").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("助手暂时不可用");
  });

  it("switches to send and queues a draft during generation", async () => {
    let resolveFirst: ((value: { sessionId: string; response: string }) => void) | undefined;
    let resolveSecond: ((value: { sessionId: string; response: string }) => void) | undefined;
    let callCount = 0;
    streamMock.mockImplementation(() => new Promise<{ sessionId: string; response: string }>((resolve) => {
      callCount += 1;
      if (callCount === 1) resolveFirst = resolve;
      else resolveSecond = resolve;
    }));
    const wrapper = mount(AssistantView, { global: { plugins: [i18n] } });
    await flushPromises();

    const textarea = wrapper.get("textarea");
    await textarea.setValue("第一句");
    void wrapper.get(".assistant-composer").trigger("submit");
    await flushPromises();

    await textarea.setValue("第二句");
    expect(wrapper.find(".assistant-stop").exists()).toBe(false);
    expect(wrapper.get(".assistant-send").attributes("type")).toBe("submit");
    await wrapper.get(".assistant-composer").trigger("submit");
    await flushPromises();

    expect(streamMock).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain("已排队 1 条");

    resolveFirst?.({ sessionId: "pwa-test", response: "第一句已完成" });
    await flushPromises();
    expect(streamMock).toHaveBeenCalledTimes(2);
    expect(streamMock.mock.calls[1]?.[0]).toBe("第二句");

    resolveSecond?.({ sessionId: "pwa-test", response: "第二句已完成" });
    await flushPromises();
    expect(wrapper.find(".assistant-progress").exists()).toBe(false);
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
