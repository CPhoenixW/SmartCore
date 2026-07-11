import { apiRequest } from "./client";
import type { Idea } from "@/types/idea";

export const ideaApi = {
  list: () => apiRequest<Idea[]>("/api/idea"),
  create: (content: string) => apiRequest<Idea>("/api/idea", { method: "POST", body: JSON.stringify({ content }) }),
  update: (id: string, payload: Partial<Pick<Idea, "content" | "handled">>) =>
    apiRequest<Idea>(`/api/idea/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  remove: (id: string) => apiRequest<Idea>(`/api/idea/${encodeURIComponent(id)}`, { method: "DELETE" }),
};
