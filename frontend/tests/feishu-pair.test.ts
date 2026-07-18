import { afterEach, describe, expect, it, vi } from "vitest";
import { feishuPairApi } from "@/api/feishuPair";

afterEach(() => vi.restoreAllMocks());

describe("feishuPairApi", () => {
  it("starts the authenticated default-bot pairing flow", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true,
      data: {
        pairId: "pair-1",
        botId: "bot-1",
        botName: "SmartCore",
        deviceName: "SmartCore",
        deviceKind: "feishuBot",
        claimCode: "claim-code",
        stat: "created",
        expiresAt: "2026-07-18T21:00:00+08:00",
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const pair = await feishuPairApi.start();

    expect(pair.deviceKind).toBe("feishuBot");
    expect(fetchMock).toHaveBeenCalledWith("/api/feishu/pair/start", expect.objectContaining({ method: "POST" }));
  });

  it("uses user-scoped binding endpoints", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true,
      data: [],
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await feishuPairApi.bindings();

    expect(fetchMock).toHaveBeenCalledWith("/api/feishu/bindings", expect.objectContaining({ method: "GET" }));
  });
});
