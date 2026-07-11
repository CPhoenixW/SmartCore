import { afterEach, describe, expect, it, vi } from "vitest";
import { aiApi } from "@/api/ai";

afterEach(() => vi.restoreAllMocks());

describe("aiApi", () => {
  it("unwraps the parsed payload returned by /api/llm/parse", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true, data: { status: "ok", scene: "create_event", text: "x", parsed: { evtType: "remind", title: "喝水" }, now: "2026-01-01", provider: "test", model: "test" } }), { status: 200, headers: { "Content-Type": "application/json" } })));
    await expect(aiApi.parse("提醒我喝水")).resolves.toEqual({ evtType: "remind", title: "喝水" });
  });
});
