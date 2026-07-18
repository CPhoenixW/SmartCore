import { afterEach, describe, expect, it, vi } from "vitest";
import { deviceApi } from "@/api/device";
import { devicePersonNames, deviceStateView } from "@/utils/device";
import { usageChartPosition, usageLineCoordinates } from "@/utils/usageChart";

afterEach(() => vi.restoreAllMocks());

describe("device utilities", () => {
  it("reads presence and people from heartbeat metadata", () => {
    const view = deviceStateView({ deviceId: "pi", state: "working", confidence: 0.9, seenAt: new Date().toISOString(), meta: { present: true, persons: [{ personId: "p1", name: "Phoenix" }] } });
    expect(view.present).toBe(true);
    expect(devicePersonNames(view)).toEqual(["Phoenix"]);
  });
  it("marks stale state as offline", () => {
    const view = deviceStateView({ deviceId: "pi", state: "working", seenAt: "2020-01-01T00:00:00+08:00", meta: {} });
    expect(view.state).toBe("offline");
  });
  it("positions all twelve line points inside the chart", () => {
    const values = [0, 1, 2, 3, 4, 5, 6, 5, 4, 3, 2, 1];
    const coordinates = usageLineCoordinates(values).split(" ");
    const peak = usageChartPosition(6, values.length, 6, 6);

    expect(coordinates).toHaveLength(12);
    expect(peak.x).toBeGreaterThan(50);
    expect(peak.y).toBe(8);
  });
  it("requests a rolling twelve-hour usage window", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true,
      data: {
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
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await deviceApi.recentUsage("pi", 12);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/devState/usage/recent?devId=pi&timezone=Asia%2FShanghai&hours=12",
      expect.objectContaining({ method: "GET" }),
    );
  });
});
