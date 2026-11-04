import { apiRequest } from "./client";
import type { MemoryCreatePayload, MemoryItem, MemoryListResponse, MemoryUpdatePayload } from "@/types/memory";

export const memoryApi = {
  list: () => apiRequest<MemoryListResponse>("/api/memory"),
  create: (payload: MemoryCreatePayload) =>
    apiRequest<MemoryItem & { created: boolean }>("/api/memory", { method: "POST", body: JSON.stringify(payload) }),
  update: (memoryId: string, payload: MemoryUpdatePayload) =>
    apiRequest<MemoryItem>(`/api/memory/${encodeURIComponent(memoryId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  remove: (memoryId: string) =>
    apiRequest<{ memoryId: string; deleted: boolean }>(`/api/memory/${encodeURIComponent(memoryId)}`, {
      method: "DELETE",
    }),
};
