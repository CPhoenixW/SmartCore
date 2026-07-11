import { apiRequest } from "./client";
import type { LogsResponse } from "@/types/log";
export const logApi = { list: (limit = 120) => apiRequest<LogsResponse>(`/api/log?limit=${limit}`) };
