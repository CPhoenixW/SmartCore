import { describe, expect, it } from "vitest";
import { dominantComputerState, durationLabel, mergeComputerTimeline, timelinePosition, timelineTicks } from "@/utils/computer";
import type { ComputerTimelinePoint } from "@/types/computer";

describe("computer usage utilities", () => {
  it("selects the objective state with the most seconds", () => {
    expect(dominantComputerState({
      startAt: "2026-07-24T00:00:00Z",
      states: { active: 20, idle: 35, locked: 5, sleeping: 0, paused: 0 },
      dominantContext: null,
      sessionId: null,
      plannedActiveSeconds: 0,
    })).toBe("idle");
  });

  it("formats durations without implying productivity", () => {
    expect(durationLabel(5_400)).toBe("1h 30m");
    expect(durationLabel(0)).toBe("0m");
    expect(durationLabel(3_900, "zh-CN")).toBe("1小时 5分钟");
  });

  it("derives evenly spaced labels from the actual visible window", () => {
    expect(timelineTicks("2026-07-24T00:00:00Z", "2026-07-24T20:00:00Z"))
      .toEqual([
        "2026-07-24T00:00:00.000Z",
        "2026-07-24T05:00:00.000Z",
        "2026-07-24T10:00:00.000Z",
        "2026-07-24T15:00:00.000Z",
        "2026-07-24T20:00:00.000Z",
      ]);
  });

  it("clamps timeline intervals to the visible window", () => {
    expect(timelinePosition(
      "2026-07-24T05:00:00Z",
      "2026-07-24T11:00:00Z",
      "2026-07-24T08:00:00Z",
      "2026-07-24T20:00:00Z",
    )).toEqual({ left: "0%", width: "25%" });
  });

  it("merges adjacent matching timeline points and splits gaps or app changes", () => {
    const point = (startAt: string, appName: string): ComputerTimelinePoint => ({
      startAt,
      states: { active: 60, idle: 0, locked: 0, sleeping: 0, paused: 0 },
      dominantContext: {
        contextId: appName,
        bundleId: appName,
        appName,
        contextKind: null,
        domain: null,
        workspace: null,
        documentName: null,
        windowTitle: null,
        titleRedacted: false,
        classification: null,
      },
      sessionId: "session-1",
      plannedActiveSeconds: 0,
    });
    const segments = mergeComputerTimeline([
      point("2026-07-24T08:00:00Z", "Code"),
      point("2026-07-24T08:01:00Z", "Code"),
      point("2026-07-24T08:03:00Z", "Code"),
      point("2026-07-24T08:04:00Z", "Safari"),
    ], (item) => item.dominantContext ? {
      key: item.dominantContext.contextId,
      label: item.dominantContext.appName,
    } : null);

    expect(segments).toEqual([
      { key: "Code", label: "Code", startAt: "2026-07-24T08:00:00.000Z", endAt: "2026-07-24T08:02:00.000Z" },
      { key: "Code", label: "Code", startAt: "2026-07-24T08:03:00.000Z", endAt: "2026-07-24T08:04:00.000Z" },
      { key: "Safari", label: "Safari", startAt: "2026-07-24T08:04:00.000Z", endAt: "2026-07-24T08:05:00.000Z" },
    ]);
  });
});
