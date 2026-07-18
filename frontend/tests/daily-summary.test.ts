import { afterEach, describe, expect, it, vi } from "vitest";
import { dailySummaryApi } from "@/api/dailySummary";

afterEach(() => vi.restoreAllMocks());

describe("dailySummaryApi", () => {
  it("queries the authenticated report by date and text", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true,
      data: [{
        summaryId: "summary-1",
        reportDate: "2026-07-19",
        content: "Finished the report",
        stat: "complete",
        createdAt: "2026-07-19T22:00:00+08:00",
        updatedAt: "2026-07-19T22:01:00+08:00",
      }],
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const reports = await dailySummaryApi.list({
      date: "2026-07-19",
      text: "Finished",
    });

    expect(reports.at(0)?.stat).toBe("complete");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/daily-summaries?date=2026-07-19&text=Finished",
      expect.objectContaining({ method: "GET" }),
    );
  });
});
