const CACHE_NAME = "smartcore-work-v7";
const SHELL_KEY = "/work/shell";
const APP_SHELL = [
  "/work/",
  "/work/manifest.webmanifest",
  "/work/favicon.png",
  "/work/icon-192.png",
  "/work/icon-512.png",
];

async function storeResponse(cacheKey, response) {
  if (!response?.ok || response.type === "opaque" || response.status === 206) return;
  const headers = new Headers(response.headers);
  // The app marks /work as no-store. Cache.put rejects those responses, so the
  // phone keeps its own copy without that directive.
  headers.delete("cache-control");
  headers.delete("expires");
  headers.delete("pragma");
  const copy = new Response(await response.clone().arrayBuffer(), {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
  const cache = await caches.open(CACHE_NAME);
  await cache.put(cacheKey, copy);
}

function isShellRequest(request) {
  return request.mode === "navigate" || request.destination === "document";
}

async function refreshShell(request) {
  const response = await fetch(request);
  const type = response.headers.get("content-type") || "";
  if (response.ok && type.includes("text/html")) await storeResponse(SHELL_KEY, response);
  return response;
}

function isStaticAsset(request, url) {
  return request.destination === "script"
    || request.destination === "style"
    || request.destination === "image"
    || request.destination === "font"
    || url.pathname.startsWith("/work/assets/");
}

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    await Promise.all(APP_SHELL.map(async (url) => {
      try {
        const response = await fetch(url, { cache: "no-store" });
        const key = url === "/work/" ? SHELL_KEY : url;
        await storeResponse(key, response);
      } catch {
        // A missing icon should not block the shell.
      }
    }));
    try {
      const response = await fetch("/work/precache.json", { cache: "no-store" });
      if (!response.ok) return;
      const files = await response.json();
      if (!Array.isArray(files)) return;
      await Promise.all(files.map(async (url) => {
        const asset = await fetch(url, { cache: "no-store" });
        await storeResponse(url, asset);
      }));
    } catch {
      // Hashed assets are stored the first time the page requests them.
    }
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  if (isShellRequest(request)) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME);
      const cached = await cache.match(SHELL_KEY);
      const refresh = refreshShell(request).catch(async () => cached || cache.match(SHELL_KEY));
      if (cached) {
        event.waitUntil(refresh);
        return cached;
      }
      return refresh;
    })());
    return;
  }
  if (isStaticAsset(request, url)) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME);
      const cached = await cache.match(request);
      const refresh = fetch(request)
        .then(async (response) => {
          await storeResponse(request, response);
          return response;
        })
        .catch(() => cached || cache.match(SHELL_KEY));
      if (cached) {
        event.waitUntil(refresh);
        return cached;
      }
      return refresh;
    })());
    return;
  }
  event.respondWith(
    fetch(request)
      .then(async (response) => {
        await storeResponse(request, response);
        return response;
      })
      .catch(() => caches.match(request).then((cached) => cached || caches.match(SHELL_KEY))),
  );
});

self.addEventListener("push", (event) => {
  const data = event.data?.json?.() || {};
  const title = data.title || "SmartCore";
  const options = {
    body: data.body || "你有一条新的提醒",
    tag: data.tag || "smartcore-notification",
    data: { url: data.url || "/work/overview" },
    icon: "/work/icon-192.png",
    badge: "/work/icon-192.png",
    renotify: true,
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/work/overview", self.location.origin).href;
  event.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
    const existing = windows.find((client) => client.url.startsWith(self.location.origin + "/work/"));
    if (existing) return existing.navigate(target).then(() => existing.focus());
    return clients.openWindow(target);
  }));
});
