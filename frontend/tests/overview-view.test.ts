import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import OverviewView from "@/views/OverviewView.vue";
import { i18n } from "@/locales";

vi.mock("@tanstack/vue-query", () => ({
  useQuery: () => ({ data: { value: [] }, isPending: { value: false }, isError: { value: false } }),
  useMutation: () => ({ mutate: vi.fn(), isPending: { value: false } }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

describe("OverviewView", () => {
  it("renders the action-focused mobile overview", () => {
    const wrapper = mount(OverviewView, {
      global: {
        plugins: [i18n],
        mocks: { $router: { push: vi.fn() } },
        stubs: { RouterLink: true },
      },
    });

    expect(wrapper.find(".overview-focus").exists()).toBe(true);
    expect(wrapper.find(".overview-assistant").exists()).toBe(true);
    expect(wrapper.find(".global-search").exists()).toBe(false);
    expect(wrapper.text()).toContain("下一项行动");
  });
});
