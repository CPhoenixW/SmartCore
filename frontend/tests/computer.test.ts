import { describe, expect, it } from "vitest";
import { dominantComputerState, durationLabel, timelinePosition } from "@/utils/computer";

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
  });

  it("clamps timeline intervals to the visible window", () => {
    expect(timelinePosition(
      "2026-07-24T05:00:00Z",
      "2026-07-24T11:00:00Z",
      "2026-07-24T08:00:00Z",
      "2026-07-24T20:00:00Z",
    )).toEqual({ left: "0%", width: "25%" });
  });
});
