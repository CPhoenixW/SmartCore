import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import NotificationInbox from "@/components/overview/NotificationInbox.vue";
import { i18n } from "@/locales";

const { pushMock, rows } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  rows: [
    {
      notifyId: "n-1",
      evtId: "evt-1",
      channel: "browser",
      title: "计划即将开始",
      content: "还有 10 分钟",
      scheduledAt: "2026-07-31T09:50:00+08:00",
      sentAt: "2026-07-31T09:50:01+08:00",
      stat: "sent",
      deliveryState: "accepted",
      deliveryDetail: "push_provider_accepted",
    },
    {
      notifyId: "n-2",
      evtId: null,
      channel: "screen",
      title: "投递失败",
      content: "屏幕离线",
      scheduledAt: "2026-07-31T09:40:00+08:00",
      sentAt: null,
      stat: "failed",
      failReason: "screen websocket offline",
    },
  ],
}));

vi.mock("@tanstack/vue-query", () => ({
  useQuery: () => ({ data: { value: rows }, isPending: { value: false }, refetch: vi.fn() }),
}));
vi.mock("@/api/notifications", () => ({ notificationsApi: { list: vi.fn() } }));
vi.mock("vue-router", () => ({ useRouter: () => ({ push: pushMock }) }));

describe("NotificationInbox", () => {
  beforeEach(() => pushMock.mockReset());

  it("shows recent deliveries with status styling and opens the related target", async () => {
    const wrapper = mount(NotificationInbox, { global: { plugins: [i18n] } });

    expect(wrapper.findAll(".notification-inbox__row")).toHaveLength(2);
    expect(wrapper.find(".notification-inbox__row--failed").exists()).toBe(true);
    expect(wrapper.text()).toContain("推送服务已接收（手机显示未确认）");
    await wrapper.find(".notification-inbox__row").trigger("click");

    expect(pushMock).toHaveBeenCalledWith({ name: "update", query: { evtId: "evt-1" } });
  });
});
