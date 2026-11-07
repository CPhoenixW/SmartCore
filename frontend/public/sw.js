const CACHE_NAME = "smartcore-work-v6";
const APP_SHELL = [
  "/work/",
  "/work/manifest.webmanifest",
  "/work/favicon.png",
  "/work/icon-192.png",
  "/work/icon-512.png",
];

async function cacheResponse(request, response) {
  if (!response?.ok || response.type === "opaque") return response;
  const cache = await caches.open(CACHE_NAME);
  await cache.put(request, response.clone());
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
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(async (cache) => {
        await cache.addAll(APP_SHELL);
        try {
          const response = await fetch("/work/precache.json", { cache: "no-store" });
          if (!response.ok) return;
          const files = await response.json();
          if (Array.isArray(files) && files.length) await cache.addAll(files);
        } catch {
          // The shell still works; hashed assets are cached on first use.
        }
      })
      .then(() => self.skipWaiting()),
  );
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
  if (isStaticAsset(request, url)) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const update = fetch(request).then((response) => cacheResponse(request, response));
        return cached || update.catch(() => caches.match("/work/"));
      }),
    );
    return;
  }
  event.respondWith(
    fetch(request)
      .then((response) => cacheResponse(request, response))
      .catch(() => caches.match(request).then((cached) => cached || caches.match("/work/"))),
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
