import { describe, expect, it } from "vitest";
import { devicePersonNames, deviceStateView } from "@/utils/device";

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
});
