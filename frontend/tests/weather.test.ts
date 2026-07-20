import { describe, expect, it } from "vitest";
import { weatherLabelKey, weatherSymbol } from "@/utils/weather";

describe("weather helpers", () => {
  it("maps WMO weather groups to compact labels and symbols", () => {
    expect(weatherLabelKey(0)).toBe("clear");
    expect(weatherLabelKey(63)).toBe("rain");
    expect(weatherLabelKey(95)).toBe("storm");
    expect(weatherSymbol(71)).toBe("🌨️");
  });
});
