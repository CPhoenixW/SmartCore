import { apiRequest } from "./client";
import type { CoursePayload } from "@/types/course";
import type { CourseEvent, PlanEvent } from "@/types/event";

export const courseApi = {
  list() {
    return apiRequest<CourseEvent[]>("/api/courseEvt");
  },
  create(payload: CoursePayload) {
    return apiRequest<CourseEvent>("/api/courseEvt", { method: "POST", body: JSON.stringify(payload) });
  },
  sync(id: string) {
    return apiRequest<{ course: CourseEvent; plans: PlanEvent[] }>(`/api/courseEvt/${encodeURIComponent(id)}/sync`, { method: "POST" });
  },
};
