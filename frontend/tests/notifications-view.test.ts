import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import NotificationsView from "@/views/NotificationsView.vue";
import { i18n } from "@/locales";

vi.mock("@/components/overview/NotificationInbox.vue", () => ({
  default: { props: ["limit"], template: "<div class=\"notification-inbox-stub\">limit={{ limit }}</div>" },
}));

describe("NotificationsView", () => {
  it("presents notifications as a standalone section", () => {
    const wrapper = mount(NotificationsView, {
      global: { plugins: [i18n], stubs: { RouterLink: true } },
    });

    expect(wrapper.find(".notifications-page").exists()).toBe(true);
    expect(wrapper.text()).toContain("通知");
    expect(wrapper.find(".notification-inbox-stub").text()).toContain("limit=50");
  });
});
