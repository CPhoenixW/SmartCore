import { flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { describe, expect, it } from "vitest";
import DevicePairPanel from "@/components/device/DevicePairPanel.vue";
import { i18n } from "@/locales";

describe("DevicePairPanel", () => {
  it("renders only the devices owned by the current user", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    queryClient.setQueryData(["lifeDevices"], [
      { deviceId: "screen-1", userId: "user-1", deviceName: "Desk display", deviceKind: "screen", stat: "active" },
      { deviceId: "computer-1", userId: "user-1", deviceName: "MacBook", deviceKind: "computer", stat: "active" },
    ]);
    const wrapper = mount(DevicePairPanel, {
      props: { allowedKinds: ["screen"] },
      global: { plugins: [[VueQueryPlugin, { queryClient }], i18n] },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Desk display");
    expect(wrapper.text()).not.toContain("MacBook");
  });
});
