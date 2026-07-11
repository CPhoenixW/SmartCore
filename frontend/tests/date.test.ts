import { describe, expect, it } from "vitest";
import { extractDateQuery, localInputToIso, normalizeSearch } from "@/utils/date";

describe("date utilities", () => {
  it("preserves a numeric timezone offset instead of serializing a bare UTC Z value", () => {
    const value = localInputToIso("2026-09-13T08:30");
    expect(value).toMatch(/^2026-09-13T08:30:00[+-]\d{2}:\d{2}$/);
  });
  it("extracts Chinese and slash-separated dates", () => {
    expect(extractDateQuery("查看 2026年9月13日 的课程")).toBe("2026-09-13");
    expect(extractDateQuery("2026/09/13 08:00")).toBe("2026-09-13");
  });
  it("normalizes Chinese clock search expressions", () => {
    expect(normalizeSearch("晚上 8点半")).toContain("08:30");
  });
});
