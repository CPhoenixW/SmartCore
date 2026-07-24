import { expect, vi, type Mock } from "vitest";

export function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify({ ok: true, data }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function mockJsonFetch(data: unknown, status = 200): Mock {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(data, status));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function restoreHttpMocks(): void {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
}

export function expectFetch(
  fetchMock: Mock,
  url: string,
  method: string,
  init: Record<string, unknown> = {},
): void {
  expect(fetchMock).toHaveBeenCalledWith(
    url,
    expect.objectContaining({ method, ...init }),
  );
}
