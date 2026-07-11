import { apiRequest } from "./client";
import type { SmartCoreEvent } from "@/types/event";

export interface EventQuery {
  date?: string;
  stat?: "todo" | "done" | "cancelled" | "all";
  includeReminders?: boolean;
}

function toQueryString(query: EventQuery): string {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined) params.set(key, String(value));
  });
  return params.toString();
}

export const eventApi = {
  list(query: EventQuery = {}) {
    const queryString = toQueryString(query);
    return apiRequest<SmartCoreEvent[]>(`/api/evt${queryString ? `?${queryString}` : ""}`);
  },
};
