import { shallowMount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ComputerUsagePanel from "@/components/device/ComputerUsagePanel.vue";
import { i18n } from "@/locales";

const { queries } = vi.hoisted(() => ({ queries: [] as Array<Record<string, unknown>> }));

vi.mock("@tanstack/vue-query", () => ({
  useQuery: (options: Record<string, unknown>) => {
    queries.push(options);
    const queryKey = options.queryKey as unknown[];
    return {
      data: {
        value: queryKey[0] === "lifeDevices"
          ? [{ deviceId: "computer-1", deviceName: "Mac", deviceKind: "computer", stat: "active" }]
          : undefined,
      },
    };
  },
}));

describe("ComputerUsagePanel", () => {
  beforeEach(() => queries.splice(0));

  it("separates overview, activity, and management into exclusive views", async () => {
    const wrapper = shallowMount(ComputerUsagePanel, { global: { plugins: [i18n] } });
    const tabs = wrapper.findAll(".computer-view-tabs button");

    expect(tabs).toHaveLength(3);
    expect(tabs[0]!.attributes("aria-selected")).toBe("true");
    expect(wrapper.find("device-metric-strip-stub").exists()).toBe(true);

    await tabs[1]!.trigger("click");
    expect(tabs[1]!.attributes("aria-selected")).toBe("true");
    expect(wrapper.find("device-metric-strip-stub").exists()).toBe(false);

    await tabs[2]!.trigger("click");
    expect(tabs[2]!.attributes("aria-selected")).toBe("true");
    const usageQuery = queries.find((item) => (item.queryKey as unknown[])[1] === "usage");
    expect((usageQuery?.enabled as { value: boolean }).value).toBe(false);
  });
});
