import { apiRequest } from "./client";
import type { Idea, IdeaUpload } from "@/types/idea";

export const ideaApi = {
  list: () => apiRequest<Idea[]>("/api/idea"),
  create: (payload: { title: string; description: string; uploadIds: string[] }) => apiRequest<Idea>("/api/idea", { method: "POST", body: JSON.stringify(payload) }),
  upload: (files: File[]) => { const body = new FormData(); files.forEach((file) => body.append("files", file)); return apiRequest<IdeaUpload[]>("/api/idea/uploads", { method: "POST", body }); },
  processMedia: (payload: { uploadIds: string[]; text: string }) => apiRequest<{ queued: boolean; uploadIds: string[] }>("/api/idea/media-process", { method: "POST", body: JSON.stringify(payload) }),
  update: (id: string, payload: Partial<Pick<Idea, "title" | "description" | "handled">>) =>
    apiRequest<Idea>(`/api/idea/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  remove: (id: string) => apiRequest<Idea>(`/api/idea/${encodeURIComponent(id)}`, { method: "DELETE" }),
};
