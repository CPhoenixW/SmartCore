import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import DailySummaryView from "@/views/DailySummaryView.vue";
import { dailySummaryApi } from "@/api/dailySummary";
import { i18n } from "@/locales";

const { report } = vi.hoisted(() => ({
  report: {
    summaryId: "summary-1",
    reportDate: "2026-07-31",
    content: "Original summary",
    stat: "complete" as const,
    generatedAt: "2026-07-31T23:59:00+08:00",
    createdAt: "2026-07-31T23:59:00+08:00",
    updatedAt: "2026-07-31T23:59:00+08:00",
  },
}));

vi.mock("@tanstack/vue-query", () => ({
  useQuery: () => ({ data: { value: [report] }, isPending: { value: false } }),
  useMutation: (options: { mutationFn: () => Promise<unknown> }) => ({
    mutate: vi.fn(() => options.mutationFn()),
    isPending: { value: false },
  }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/api/dailySummary", () => ({
  dailySummaryApi: {
    list: vi.fn(),
    update: vi.fn().mockResolvedValue(report),
  },
}));

describe("DailySummaryView", () => {
  it("edits the current owner-scoped summary", async () => {
    const wrapper = mount(DailySummaryView, { global: { plugins: [i18n] } });

    await wrapper.get(".card-actions .button").trigger("click");
    const editor = wrapper.get(".daily-summary-editor textarea");
    expect((editor.element as HTMLTextAreaElement).value).toBe("Original summary");

    await editor.setValue("Revised summary");
    await wrapper.get(".daily-summary-editor").trigger("submit");

    expect(dailySummaryApi.update).toHaveBeenCalledWith("summary-1", {
      content: "Revised summary",
      expectedUpdatedAt: "2026-07-31T23:59:00+08:00",
    });
  });
});
