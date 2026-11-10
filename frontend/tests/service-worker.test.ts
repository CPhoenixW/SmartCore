import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { describe, expect, it, vi } from "vitest";

const source = readFileSync("public/sw.js", "utf-8");
const origin = "https://smartcore.example";

function createWorker() {
  const entries = new Map<string, Map<string, Response>>();
  const listeners = new Map<string, (event: any) => void>();
  const postMessage = vi.fn();
  const fetch = vi.fn();
  const skipWaiting = vi.fn();
  const key = (request: string | Request) => typeof request === "string" ? request : request.url;
  const caches = {
    open: async (name: string) => {
      if (!entries.has(name)) entries.set(name, new Map());
      const cache = entries.get(name)!;
      return {
        match: async (request: string | Request) => cache.get(key(request))?.clone(),
        put: async (request: string | Request, response: Response) => {
          cache.set(key(request), response.clone());
        },
      };
    },
  };
  const context = {
    self: {
      location: { origin },
      addEventListener: (name: string, listener: (event: any) => void) => listeners.set(name, listener),
      clients: { matchAll: async () => [{ postMessage }] },
      skipWaiting,
    },
    caches, fetch, Headers, Response, URL,
  };
  const refreshShell = runInNewContext(`${source}\nrefreshShell`, context) as (request: Request) => Promise<Response>;
  return { caches, fetch, listeners, postMessage, refreshShell, skipWaiting };
}

const shell = (html: string) => new Response(html, { headers: { "Content-Type": "text/html" } });

describe("service worker", () => {
  it("notifies clients once after a changed shell and keeps its updated copy", async () => {
    const worker = createWorker();
    const cache = await worker.caches.open("smartcore-work-v11");
    await cache.put("/work/shell", shell("<script src='old.js'></script>"));
    worker.fetch.mockImplementation(async () => shell("<script src='new.js'></script>"));

    await Promise.all([
      worker.refreshShell(new Request(`${origin}/work/assistant`)),
      worker.refreshShell(new Request(`${origin}/work/assistant`)),
    ]);
    await worker.refreshShell(new Request(`${origin}/work/assistant`));

    expect(worker.postMessage).toHaveBeenCalledExactlyOnceWith({ shellUpdated: true });
    expect(await (await cache.match("/work/shell"))?.text()).toContain("new.js");
  });

  it("does not notify for a first shell download", async () => {
    const worker = createWorker();
    worker.fetch.mockResolvedValue(shell("<html>first</html>"));

    await worker.refreshShell(new Request(`${origin}/work/assistant`));

    expect(worker.postMessage).not.toHaveBeenCalled();
  });

  it("immediately serves a cached shell while its network refresh is pending", async () => {
    const worker = createWorker();
    const cache = await worker.caches.open("smartcore-work-v11");
    await cache.put("/work/shell", shell("<html>cached</html>"));
    worker.fetch.mockImplementation(() => new Promise(() => {}));
    let response: Promise<Response> | undefined;

    worker.listeners.get("fetch")!({
      request: { method: "GET", url: `${origin}/work/assistant`, mode: "navigate" },
      respondWith: (result: Promise<Response>) => { response = result; },
      waitUntil: vi.fn(),
    });

    expect(await (await response)?.text()).toBe("<html>cached</html>");
  });

  it("reuses existing fingerprinted asset cache and leaves API requests alone", async () => {
    const worker = createWorker();
    const request = { method: "GET", url: `${origin}/work/assets/index-old.js`, destination: "script" };
    const cache = await worker.caches.open("smartcore-work-v10");
    await cache.put(request as Request, new Response("cached script"));
    let response: Promise<Response> | undefined;
    worker.listeners.get("fetch")!({
      request,
      respondWith: (result: Promise<Response>) => { response = result; },
    });

    expect(await (await response)?.text()).toBe("cached script");
    expect(worker.fetch).not.toHaveBeenCalled();
    const respondWith = vi.fn();
    worker.listeners.get("fetch")!({
      request: { method: "GET", url: `${origin}/api/evt` }, respondWith,
    });
    expect(respondWith).not.toHaveBeenCalled();
  });
});
