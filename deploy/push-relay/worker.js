export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("method not allowed", { status: 405 });
    }
    if (!authorized(request, env)) {
      return new Response("unauthorized", { status: 401 });
    }
    let payload;
    try {
      payload = await request.json();
    } catch {
      return new Response("invalid json", { status: 400 });
    }
    const target = allowedTarget(payload.url);
    if (!target) {
      return new Response("forbidden", { status: 403 });
    }
    const body = decodeBody(payload.body);
    if (body === null) {
      return new Response("invalid body", { status: 400 });
    }
    const headers = forwardedHeaders(payload.headers);
    try {
      const upstream = await fetch(target, {
        method: "POST",
        headers,
        body,
        redirect: "manual",
        signal: AbortSignal.timeout(10000),
      });
      const text = await upstream.text();
      return new Response(text, {
        status: upstream.status,
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    } catch {
      return new Response("upstream unreachable", { status: 502 });
    }
  },
};

function authorized(request, env) {
  const token = String(env.RELAY_TOKEN || "");
  const actual = request.headers.get("authorization") || "";
  const expected = `Bearer ${token}`;
  if (!token || expected.length !== actual.length) return false;
  let diff = 0;
  for (let index = 0; index < expected.length; index += 1) {
    diff |= expected.charCodeAt(index) ^ actual.charCodeAt(index);
  }
  return diff === 0;
}

function allowedTarget(value) {
  let url;
  try {
    url = new URL(String(value || ""));
  } catch {
    return "";
  }
  if (url.protocol !== "https:" || url.username || url.password) return "";
  if (url.hostname !== "fcm.googleapis.com") return "";
  if (!url.pathname.startsWith("/fcm/send/") && !url.pathname.startsWith("/wp/")) return "";
  return url.toString();
}

function decodeBody(value) {
  if (value == null || value === "") return new Uint8Array();
  if (typeof value !== "string" || value.length > 16384) return null;
  try {
    const binary = atob(value);
    if (binary.length > 8192) return null;
    return Uint8Array.from(binary, (char) => char.charCodeAt(0));
  } catch {
    return null;
  }
}

function forwardedHeaders(value) {
  const allowed = new Set([
    "authorization",
    "content-encoding",
    "content-type",
    "crypto-key",
    "encryption",
    "ttl",
    "urgency",
    "topic",
  ]);
  const headers = new Headers();
  if (!value || typeof value !== "object") return headers;
  for (const [key, raw] of Object.entries(value)) {
    if (allowed.has(String(key).toLowerCase())) headers.set(key, String(raw));
  }
  return headers;
}
