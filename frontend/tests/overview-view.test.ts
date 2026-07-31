import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import OverviewView from "@/views/OverviewView.vue";
import { i18n } from "@/locales";

vi.mock("@tanstack/vue-query", () => ({
  useQuery: (options: { queryKey: unknown }) => {
    const key = Array.isArray(options.queryKey) ? options.queryKey[0] : "";
    return {
      data: { value: key === "ideas" ? [{
        ideaId: "idea-overview",
        title: "Recent idea",
        description: "Shared card treatment",
        handled: false,
        revision: 1,
        attachments: [],
        createdAt: "2026-07-31T10:00:00+08:00",
      }] : undefined },
      isPending: { value: false },
      isError: { value: false },
    };
  },
  useMutation: () => ({ mutate: vi.fn(), isPending: { value: false } }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

describe("OverviewView", () => {
  it("renders recent ideas with the shared idea card", () => {
    const wrapper = mount(OverviewView, {
      global: {
        plugins: [i18n],
        mocks: { $router: { push: vi.fn() } },
        stubs: { RouterLink: true },
      },
    });

    expect(wrapper.get(".idea-card").text()).toContain("Recent idea");
    expect(wrapper.get(".idea-card").text()).toContain("Shared card treatment");
    expect(wrapper.findAll(".overview-scroll-card")).toHaveLength(2);
    expect(wrapper.findAll(".overview-scroll-window")).toHaveLength(2);
  });
});
