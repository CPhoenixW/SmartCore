import { apiRequest, buildQuery } from "./client";
import type {
  CreateDdlPayload,
  CreatePlanPayload,
  CreateReminderPayload,
  EventQuery,
  SmartCoreEvent,
  UpdateEventPayload,
} from "@/types/event";

export const eventApi = {
  list(query: EventQuery = {}) {
    return apiRequest<SmartCoreEvent[]>(`/api/evt${buildQuery(query)}`);
  },
  read(id: string) {
    return apiRequest<SmartCoreEvent>(`/api/evt/${encodeURIComponent(id)}`);
  },
  createPlan(payload: CreatePlanPayload) {
    return apiRequest<SmartCoreEvent>("/api/planEvt", { method: "POST", body: JSON.stringify(payload) });
  },
  createReminder(payload: CreateReminderPayload) {
    return apiRequest<SmartCoreEvent>("/api/remindEvt", { method: "POST", body: JSON.stringify(payload) });
  },
  createDdl(payload: CreateDdlPayload) {
    return apiRequest<SmartCoreEvent>("/api/ddlEvt", { method: "POST", body: JSON.stringify(payload) });
  },
  update(id: string, payload: UpdateEventPayload | Record<string, unknown>) {
    return apiRequest<SmartCoreEvent>(`/api/evt/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  cancel(id: string) {
    return apiRequest<SmartCoreEvent>(`/api/evt/${encodeURIComponent(id)}`, { method: "DELETE" });
  },
};
