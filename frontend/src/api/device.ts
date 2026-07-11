import { apiRequest, buildQuery } from "./client";
import type { DeviceState, DeviceUsage, PhotoRequest } from "@/types/device";

export const deviceApi = {
  latest: (devId = "pi") => apiRequest<DeviceState | null>(`/api/devState/latest${buildQuery({ devId })}`),
  recent: (devId = "pi", limit = 120) => apiRequest<DeviceState[]>(`/api/devState/recent${buildQuery({ devId, limit })}`),
  usageToday: (devId = "pi") => apiRequest<DeviceUsage>(`/api/devState/usage/today${buildQuery({ devId, timezone: "Asia/Shanghai" })}`),
  requestPhoto: (devId = "pi") => apiRequest<PhotoRequest>(`/api/device/${encodeURIComponent(devId)}/photoRequest`, {
    method: "POST",
    body: JSON.stringify({ reason: "work-panel" }),
  }),
  photoRequests: (devId = "pi") => apiRequest<PhotoRequest[]>(`/api/device/${encodeURIComponent(devId)}/photoRequests?limit=20`),
  photoImageUrl: (id: string) => `/api/device/photoRequest/${encodeURIComponent(id)}/image`,
};
