import { apiRequest } from "./client";

export interface RuntimeClock {
  serverNow: string;
  utcNow: string;
  timezone: string;
  offsetMinutes: number;
  source: "server";
}

export const runtimeApi = {
  clock: (timezone?: string) => apiRequest<RuntimeClock>(`/api/runtime/clock${timezone ? `?timezone=${encodeURIComponent(timezone)}` : ""}`),
};
