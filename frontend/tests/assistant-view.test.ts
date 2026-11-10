import { enableAutoUnmount, flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AssistantView from "@/views/AssistantView.vue";
import { i18n } from "@/locales";

const { streamMock, listMock, readMock, routeMock, invalidateMock } = vi.hoisted(() => ({
  streamMock: vi.fn(),
  listMock: vi.fn(),
  readMock: vi.fn(),
  routeMock: { query: {} as Record<string, string> },
  invalidateMock: vi.fn(),
}));

vi.mock("@tanstack/vue-query", () => ({ useQueryClient: () => ({ invalidateQueries: invalidateMock }) }));

vi.mock("vue-router", async (importOriginal) => ({
  ...await importOriginal<typeof import("vue-router")>(),
  useRoute: () => routeMock,
}));

vi.mock("@/api/assistant", () => ({
  assistantApi: { stream: streamMock, list: listMock, read: readMock },
}));

enableAutoUnmount(afterEach);
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function makeConversation(count: number) {
  return {
    conversationId: "pwa-test", title: "滚动测试", stat: "active" as const,
    createdAt: "2026-07-31T10:00:00+08:00", updatedAt: "2026-07-31T12:00:00+08:00",
    messages: Array.from({ length: count }, (_, index) => ({
      messageId: `history-${index}`, conversationId: "pwa-test", role: "assistant" as const,
      text: `历史消息 ${index}`, stat: "complete" as const,
      createdAt: new Date(new Date("2026-07-31T10:00:00+08:00").getTime() + index * 60_000).toISOString(),
    })),
  };
}

describe("AssistantView", () => {
beforeEach(() => {
  window.localStorage.clear();
  routeMock.query = {};
  invalidateMock.mockReset().mockResolvedValue(undefined);
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
    for (const key of ["overview", "events", "schedule", "ideas", "notifications"]) {
      expect(invalidateMock).toHaveBeenCalledWith({ queryKey: [key], refetchType: "none" });
    }
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

  it("keeps the bottom after cached history is replaced by fresh history and content grows", async () => {
    window.localStorage.setItem("smartcore:assistant:primary:v2", JSON.stringify(makeConversation(2)));
    let resolveHistory: ((value: ReturnType<typeof makeConversation>) => void) | undefined;
    readMock.mockImplementationOnce(() => new Promise((resolve) => { resolveHistory = resolve; }));
    let onResize: (() => void) | undefined;
    const disconnect = vi.fn();
    vi.stubGlobal("ResizeObserver", class {
      constructor(callback: () => void) { onResize = callback; }
      observe = vi.fn();
      disconnect = disconnect;
    });
    const wrapper = mount(AssistantView, { global: { plugins: [i18n] } });
    await flushPromises();
    const root = wrapper.get(".assistant-messages").element as HTMLElement;
    let height = 600;
    Object.defineProperties(root, {
      scrollHeight: { configurable: true, get: () => height },
      clientHeight: { configurable: true, value: 400 },
    });
    resolveHistory?.(makeConversation(45));
    await flushPromises();
    expect(root.scrollTop).toBe(600);
    expect(wrapper.findAll(".assistant-message")).toHaveLength(40);

    height = 1100;
    onResize?.();
    await flushPromises();
    expect(root.scrollTop).toBe(1100);

    root.scrollTop = 200;
    await wrapper.get(".assistant-messages").trigger("scroll");
    height = 1400;
    onResize?.();
    await flushPromises();
    expect(root.scrollTop).toBe(200);
    wrapper.unmount();
    expect(disconnect).toHaveBeenCalledOnce();
  });

  it("reveals a notification target outside the latest forty messages before scrolling", async () => {
    routeMock.query = { messageId: "history-2" };
    readMock.mockResolvedValueOnce(makeConversation(85));
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const top = this.id === "assistant-message-history-2" ? 1000 : 0;
      return { top, bottom: top + 100, left: 0, right: 300, width: 300, height: 100, x: 0, y: top, toJSON: () => ({}) };
    });
    const wrapper = mount(AssistantView, { global: { plugins: [i18n] } });
    const root = wrapper.get(".assistant-messages").element as HTMLElement;
    Object.defineProperty(root, "clientHeight", { configurable: true, value: 600 });
    await flushPromises();
    expect(wrapper.find("#assistant-message-history-2").exists()).toBe(true);
    expect(wrapper.get("#assistant-message-history-2").classes()).toContain("assistant-message--highlight");
    expect(wrapper.findAll(".assistant-message")).toHaveLength(83);
    expect(wrapper.find("#assistant-message-history-0").exists()).toBe(false);
    expect(root.scrollTop).toBe(750);
  });

  it("reveals an older quoted message and keeps the selected history visible after sync", async () => {
    const history = makeConversation(85);
    const latest = { ...history.messages[84]!, replyToMessageId: "history-2", replyToText: "历史消息 2" };
    history.messages[84] = latest;
    readMock.mockResolvedValue(history);
    const wrapper = mount(AssistantView, { global: { plugins: [i18n] } });
    await flushPromises();
    expect(wrapper.find("#assistant-message-history-2").exists()).toBe(false);
    await wrapper.get(".assistant-message__quote").trigger("click");
    await flushPromises();
    expect(wrapper.get("#assistant-message-history-2").classes()).toContain("assistant-message--highlight");

    readMock.mockResolvedValue(makeConversation(86));
    window.dispatchEvent(new Event("focus"));
    await flushPromises();
    expect(wrapper.find("#assistant-message-history-2").exists()).toBe(true);
    expect(wrapper.find("#assistant-message-history-85").exists()).toBe(true);
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
    expect(invalidateMock).toHaveBeenCalledWith({ queryKey: ["overview"], refetchType: "none" });
    expect(invalidateMock).toHaveBeenCalledWith({ queryKey: ["notifications"], refetchType: "none" });
  });

  it("switches to send and queues a draft during generation", async () => {
    invalidateMock.mockImplementation(() => new Promise(() => {}));
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
