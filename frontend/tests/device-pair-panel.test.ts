import { flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { describe, expect, it } from "vitest";
import DevicePairPanel from "@/components/device/DevicePairPanel.vue";
import { i18n } from "@/locales";

describe("DevicePairPanel", () => {
  it("does not render cached Feishu bindings on another device page", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    queryClient.setQueryData(["lifeDevices"], [
      { deviceId: "screen-1", userId: "user-1", deviceName: "Desk display", deviceKind: "screen", stat: "active" },
      { deviceId: "computer-1", userId: "user-1", deviceName: "MacBook", deviceKind: "computer", stat: "active" },
    ]);
    queryClient.setQueryData(["userFeishuBindings"], [
      { bindId: "bind-1", botId: "bot-1", botName: "Cached Feishu bot", chatType: "p2p", chatHint: "user", stat: "active", isPrimary: true, createdAt: "2026-07-25T00:00:00Z" },
    ]);

    const wrapper = mount(DevicePairPanel, {
      props: { allowedKinds: ["screen"] },
      global: { plugins: [[VueQueryPlugin, { queryClient }], i18n] },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Desk display");
    expect(wrapper.text()).not.toContain("MacBook");
    expect(wrapper.text()).not.toContain("Cached Feishu bot");
  });
});
