import { apiRequest } from "./client";

export interface LifeDevice { deviceId: string; userId: string; deviceName: string; deviceKind: string; stat: string; lastSeenAt?: string | null; }
export interface DevicePair { pairId: string; deviceName: string; deviceKind: string; stat: string; claimCode: string; expiresAt: string; }

export const deviceRegistryApi = {
  list: () => apiRequest<LifeDevice[]>("/api/device"),
  startPair: (deviceName: string, deviceKind: string) => apiRequest<DevicePair>("/api/device/pair/start", { method: "POST", body: JSON.stringify({ deviceName, deviceKind }) }),
  readPair: (pairId: string) => apiRequest<DevicePair>(`/api/device/pair/${pairId}`),
  confirmPair: (pairId: string) => apiRequest<DevicePair>(`/api/device/pair/${pairId}/confirm`, { method: "POST" }),
};
