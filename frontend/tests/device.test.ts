import { describe, expect, it } from "vitest";
import { devicePersonNames, deviceStateView } from "@/utils/device";
import { usageChartPosition, usageLineCoordinates } from "@/utils/usageChart";

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
});
