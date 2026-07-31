import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import IdeaView from "@/views/IdeaView.vue";
import { i18n } from "@/locales";
import type { Idea } from "@/types/idea";

const { ideas } = vi.hoisted(() => ({ ideas: [
  {
    ideaId: "idea-1",
    title: "Focused idea",
    description: "Only one representation should be visible.",
    handled: false,
    revision: 1,
    attachments: [],
    createdAt: "2026-07-31T10:00:00+08:00",
  },
] as Idea[] }));

vi.mock("@tanstack/vue-query", () => ({
  useQuery: () => ({ data: { value: ideas } }),
  useMutation: () => ({ mutate: vi.fn(), isPending: { value: false } }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

describe("IdeaView", () => {
  it("previews the first idea and opens the new editor only after the user asks", async () => {
    const wrapper = mount(IdeaView, { global: { plugins: [i18n] } });

    expect(wrapper.get(".idea-layout").classes()).toContain("split-scroll-layout");
    expect(wrapper.get(".idea-list-pane").classes()).toContain("split-scroll-column--main");
    expect(wrapper.get(".idea-detail").classes()).toContain("split-scroll-column--side");
    expect(wrapper.find(".idea-detail .form-grid").exists()).toBe(false);
    expect(wrapper.get(".idea-detail-copy").text()).toContain("Only one representation");
    expect(wrapper.find(".idea-empty-detail").exists()).toBe(false);

    await wrapper.get(".page-heading .button--primary").trigger("click");
    expect(wrapper.find(".idea-detail .form-grid").exists()).toBe(true);
    expect(wrapper.find(".idea-empty-detail").exists()).toBe(false);

    await wrapper.get(".idea-detail .form-actions .button").trigger("click");
    expect(wrapper.find(".idea-detail .form-grid").exists()).toBe(false);
    expect(wrapper.find(".idea-detail-copy").exists()).toBe(true);
  });

  it("shows either the detail or editor for a selected idea", async () => {
    const wrapper = mount(IdeaView, { global: { plugins: [i18n] } });
    await wrapper.get(".idea-card").trigger("click");

    expect(wrapper.find(".idea-detail-copy").exists()).toBe(true);
    expect(wrapper.find(".idea-detail .form-grid").exists()).toBe(false);

    await wrapper.get(".idea-detail .card-actions .preview-action-button").trigger("click");
    expect(wrapper.find(".idea-detail-copy").exists()).toBe(false);
    expect(wrapper.find(".idea-detail .form-grid").exists()).toBe(true);
  });

  it("opens the editor directly on a double click", async () => {
    const wrapper = mount(IdeaView, { global: { plugins: [i18n] } });
    await wrapper.get(".idea-card").trigger("dblclick");

    expect(wrapper.find(".idea-detail-copy").exists()).toBe(false);
    expect(wrapper.find(".idea-detail .form-grid").exists()).toBe(true);
  });
});
