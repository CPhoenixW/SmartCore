import { apiRequest, buildQuery } from "./client";
import type { ComputerMonitorStatus, ComputerUsageRange, ComputerUsageReport } from "@/types/computer";

export const computerApi = {
  status: (deviceId: string) => apiRequest<ComputerMonitorStatus | null>(`/api/computer/status${buildQuery({ deviceId })}`),
  usage: (deviceId: string, range: ComputerUsageRange, timezone: string) => apiRequest<ComputerUsageReport>(
    `/api/computer/usage${buildQuery({ deviceId, range, timezone })}`,
  ),
};
