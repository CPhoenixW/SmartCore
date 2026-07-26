import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { devicePersonNames, deviceStateView } from "@/utils/device";
import { router } from "@/router";
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

describe("device routes", () => {
  it("separates the four device domains and keeps the old entry route", () => {
    expect(router.resolve({ name: "device" }).path).toBe("/device");
    expect(router.resolve({ name: "deviceRaspberryPi" }).path).toBe("/device/raspberry-pi");
    expect(router.resolve({ name: "deviceComputer" }).path).toBe("/device/computer");
    expect(router.resolve({ name: "deviceScreen" }).path).toBe("/device/screen");
    expect(router.resolve({ name: "deviceFeishuBot" }).path).toBe("/device/feishu-bot");
  });

  it("keeps the Feishu page focused on outcomes instead of exposing a processing chain", () => {
    const source = readFileSync(resolve(process.cwd(), "src/views/FeishuBotView.vue"), "utf8");
    expect(source).not.toContain("处理链路");
    expect(source.toLowerCase()).not.toContain("processing chain");
  });

  it("keeps device pages focused on data without duplicate page headers", () => {
    for (const view of ["ComputerView.vue", "RaspberryPiView.vue", "ScreenView.vue", "FeishuBotView.vue"]) {
      const source = readFileSync(resolve(process.cwd(), `src/views/${view}`), "utf8");
      expect(source).not.toContain("<PageHeader");
    }

    const computerPanel = readFileSync(resolve(process.cwd(), "src/components/device/ComputerUsagePanel.vue"), "utf8");
    expect(computerPanel).not.toContain('<section v-if="monitor" class="computer-live-summary">');
    expect(computerPanel).toContain('label: t("computer.activeTime")');
  });
});
