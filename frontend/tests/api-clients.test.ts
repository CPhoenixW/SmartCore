import { afterEach, describe, expect, it } from "vitest";
import { aiApi } from "@/api/ai";
import { dailySummaryApi } from "@/api/dailySummary";
import { computerApi } from "@/api/computer";
import { deviceApi } from "@/api/device";
import { feishuPairApi } from "@/api/feishuPair";
import { expectFetch, mockJsonFetch, restoreHttpMocks } from "./helpers/http";

afterEach(restoreHttpMocks);

describe("API clients", () => {
  it("unwraps the parsed payload returned by /api/llm/parse", async () => {
    mockJsonFetch({
      status: "ok",
      scene: "create_event",
      text: "x",
      parsed: { evtType: "remind", title: "喝水" },
      now: "2026-01-01",
      provider: "test",
      model: "test",
    });

    await expect(aiApi.parse("提醒我喝水")).resolves.toEqual({
      evtType: "remind",
      title: "喝水",
    });
  });

  it("queries the authenticated report by date and text", async () => {
    const fetchMock = mockJsonFetch([
      {
        summaryId: "summary-1",
        reportDate: "2026-07-19",
        content: "Finished the report",
        stat: "complete",
        createdAt: "2026-07-19T22:00:00+08:00",
        updatedAt: "2026-07-19T22:01:00+08:00",
      },
    ]);

    const reports = await dailySummaryApi.list({
      date: "2026-07-19",
      text: "Finished",
    });

    expect(reports.at(0)?.stat).toBe("complete");
    expectFetch(
      fetchMock,
      "/api/daily-summaries?date=2026-07-19&text=Finished",
      "GET",
    );
  });

  it("updates a daily summary with its current timestamp", async () => {
    const fetchMock = mockJsonFetch({
      summaryId: "summary-1",
      reportDate: "2026-07-19",
      content: "Updated summary",
      stat: "complete",
      createdAt: "2026-07-19T22:00:00+08:00",
      updatedAt: "2026-07-19T22:05:00+08:00",
    });

    await dailySummaryApi.update("summary-1", {
      content: "Updated summary",
      expectedUpdatedAt: "2026-07-19T22:01:00+08:00",
    });

    expectFetch(fetchMock, "/api/daily-summaries/summary-1", "PATCH", {
      body: JSON.stringify({
        content: "Updated summary",
        expectedUpdatedAt: "2026-07-19T22:01:00+08:00",
      }),
    });
  });

  it("requests a rolling twelve-hour usage window", async () => {
    const fetchMock = mockJsonFetch({
      deviceId: "pi",
      timezone: "Asia/Shanghai",
      windowStart: "2026-07-19T14:00:00+08:00",
      windowEnd: "2026-07-20T01:30:00+08:00",
      generatedAt: "2026-07-20T01:30:00+08:00",
      points: [],
      rangeHours: 12,
      totalMinutes: 0,
      peakStartAt: null,
      averageConfidence: null,
      sampleCount: 0,
    });

    await deviceApi.recentUsage("pi", 12);

    expectFetch(
      fetchMock,
      "/api/devState/usage/recent?devId=pi&timezone=Asia%2FShanghai&hours=12",
      "GET",
    );
  });

  it("queries owner-scoped computer usage with an explicit range and timezone", async () => {
    const fetchMock = mockJsonFetch({ deviceId: "mac-1", range: "7d", timezone: "Asia/Singapore" });

    await computerApi.usage("mac-1", "7d", "Asia/Singapore");

    expectFetch(
      fetchMock,
      "/api/computer/usage?deviceId=mac-1&range=7d&timezone=Asia%2FSingapore",
      "GET",
    );
  });

  it("starts the authenticated default-bot pairing flow", async () => {
    const fetchMock = mockJsonFetch({
      pairId: "pair-1",
      botId: "bot-1",
      botName: "SmartCore",
      deviceName: "SmartCore",
      deviceKind: "feishuBot",
      claimCode: "claim-code",
      stat: "created",
      expiresAt: "2026-07-18T21:00:00+08:00",
    });

    const pair = await feishuPairApi.start();

    expect(pair.deviceKind).toBe("feishuBot");
    expectFetch(fetchMock, "/api/feishu/pair/start", "POST");
  });

  it("uses user-scoped binding endpoints", async () => {
    const fetchMock = mockJsonFetch([]);

    await feishuPairApi.bindings();

    expectFetch(fetchMock, "/api/feishu/bindings", "GET");
  });

  it("queries owner-scoped Feishu usage without requesting raw message content", async () => {
    const fetchMock = mockJsonFetch({
      range: "7d",
      timezone: "Asia/Singapore",
      totals: { messages: 0, forwarded: 0, failed: 0, unsupported: 0, notificationsSent: 0, notificationsFailed: 0 },
      intents: [],
      trend: [],
      recent: [],
    });

    await feishuPairApi.usage("7d", "Asia/Singapore");

    expectFetch(fetchMock, "/api/feishu/usage?range=7d&timezone=Asia%2FSingapore", "GET");
  });
});
