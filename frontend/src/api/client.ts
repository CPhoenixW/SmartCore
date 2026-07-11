import type { ApiEnvelope, ApiErrorBody } from "@/types/api";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

function detailText(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value;
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) return String(item.msg);
        return JSON.stringify(item);
      })
      .join("; ");
  }
  if (value && typeof value === "object") return JSON.stringify(value);
  return "Unknown API error";
}

export function buildQuery<T extends object>(params: T): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params as Record<string, unknown>)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) search.append(key, String(item));
    } else {
      search.set(key, String(value));
    }
  }
  const result = search.toString();
  return result ? `?${result}` : "";
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const method = String(options.method ?? "GET").toUpperCase();
  const response = await fetch(path, {
    ...options,
    method,
    headers,
    cache: options.cache ?? (method === "GET" ? "no-store" : undefined),
  });
  const body = (await response.json().catch(() => null)) as ApiEnvelope<T> | ApiErrorBody | null;
  if (!response.ok || body?.ok === false) {
    throw new ApiError(response.status, detailText(body?.detail ?? `HTTP ${response.status}`));
  }
  if (!body || !("data" in body)) throw new ApiError(response.status, "Invalid API response");
  return body.data as T;
}
