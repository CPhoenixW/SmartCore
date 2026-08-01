import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { mount } from "@vue/test-utils";
import BarChart from "@/components/base/BarChart.vue";
import { devicePersonNames, deviceStateView } from "@/utils/device";
import { router } from "@/router";
import { scrollToLatest } from "@/utils/scroll";

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
  it("positions horizontal histories at their latest data", () => {
    const element = { scrollLeft: 0, scrollWidth: 960 };

    scrollToLatest(element);
    expect(element.scrollLeft).toBe(960);
  });
});

describe("device charts", () => {
  it("renders focusable bars with value details", () => {
    const wrapper = mount(BarChart, {
      props: {
        labels: ["09:00", "10:00"],
        details: ["09:00–10:00", "10:00–11:00"],
        label: "Usage",
        series: [{ key: "usage", name: "Minutes", color: "#2563eb", values: [10, 20] }],
      },
    });

    const bars = wrapper.findAll(".bar-chart__bar");
    expect(bars).toHaveLength(2);
    expect(bars[0]?.attributes("data-tooltip")).toBe("09:00–10:00 · Minutes: 10");
    expect(bars[1]?.attributes("style")).toContain("height: 100%");
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

    const computerView = readFileSync(resolve(process.cwd(), "src/views/ComputerView.vue"), "utf8");
    expect(computerView).toContain('import ComputerUsagePanel from "@/components/device/ComputerUsagePanel.vue"');

    const computerPanel = readFileSync(resolve(process.cwd(), "src/components/device/ComputerUsagePanel.vue"), "utf8");
    expect(computerPanel).not.toContain('<section v-if="monitor" class="computer-live-summary">');
    expect(computerPanel).toContain('label: t("computer.activeTime")');
  });

  it("keeps dense device histories scrollable and uses the read-only screen preview", () => {
    const piView = readFileSync(resolve(process.cwd(), "src/views/RaspberryPiView.vue"), "utf8");
    const computerPanel = readFileSync(resolve(process.cwd(), "src/components/device/ComputerUsagePanel.vue"), "utf8");
    const screenView = readFileSync(resolve(process.cwd(), "src/views/ScreenView.vue"), "utf8");
    const styles = readFileSync(resolve(process.cwd(), "src/styles/workbench.css"), "utf8");

    expect(piView).toContain('class="log-list device-scroll-list"');
    expect(piView).not.toContain("logs.slice(");
    expect(computerPanel).toContain('class="computer-map-index"');
    expect(computerPanel).toContain('computerApi.usage(selectedDeviceId.value, "24h", timezone)');
    expect(computerPanel).toContain("computer-two-column computer-two-column--scroll");
    expect(computerPanel).toContain("computer-card-scroll");
    expect(computerPanel).toContain('ref="activityMapScroll"');
    expect(styles).toContain(".computer-two-column--scroll>.card{display:flex;height:300px");
    expect(styles).toContain(".computer-two-column--scroll>.card>.card-body{min-height:0;flex:1;overflow:hidden}");
    expect(styles).toContain(".computer-card-scroll{align-content:start;height:100%;overflow-y:auto");
    expect(screenView).toContain('src="/screen?preview=1"');
    expect(screenView).toContain('class="screen-preview-status"');
    expect(screenView).not.toContain("DeviceMetricStrip");
    expect(screenView).not.toContain('t("screenDevice.parameters")');
  });

  it("uses continuous work blocks as the primary computer insight", () => {
    const source = readFileSync(resolve(process.cwd(), "src/components/device/ComputerUsagePanel.vue"), "utf8");

    expect(source).toContain("computer.currentWorkBlock");
    expect(source).toContain("computer.projectInvestment");
    expect(source).toContain("project.codexReports");
    expect(source).toContain("computer.recentWorkBlocks");
    expect(source).toContain('.filter((block) => block.status === "closed")');
    expect(source).toContain(".slice(0, 4)");
    expect(source).toContain("showHourlyEvidence");
    expect(source).not.toContain("computer.moreInsights");
    expect(source).not.toContain("computer.planExecution");
    expect(source).not.toContain("computer.dailyWorkLog");
    expect(source).toContain("computer.recentWorkBlocksNote");
    expect(source).toContain("DeviceManagementPanel");
  });

  it("uses interactive bars for all time-series charts", () => {
    const piView = readFileSync(resolve(process.cwd(), "src/views/RaspberryPiView.vue"), "utf8");
    const computerPanel = readFileSync(resolve(process.cwd(), "src/components/device/ComputerUsagePanel.vue"), "utf8");
    const feishuView = readFileSync(resolve(process.cwd(), "src/views/FeishuBotView.vue"), "utf8");
    const styles = readFileSync(resolve(process.cwd(), "src/styles/workbench.css"), "utf8");

    for (const source of [piView, computerPanel, feishuView]) {
      expect(source).toContain("BarChart");
      expect(source).not.toContain("SmoothLineChart");
    }
    expect(piView).toContain("recentUsage(activeDeviceId.value, 24)");
    expect(feishuView).not.toContain("feishuDevice.recentMessages");
    expect(feishuView).toContain("feishu-binding-management");
    expect(styles).toContain(".bar-chart__canvas{display:grid;align-items:end;height:134px");
    expect(styles).toContain(".bar-chart__labels{display:grid;min-height:16px");
  });
});
