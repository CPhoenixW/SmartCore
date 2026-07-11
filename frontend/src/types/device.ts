export interface DeviceState {
  deviceId: string;
  state: "working" | "away" | "offline" | "unknown" | string;
  confidence?: number | null;
  seenAt: string;
  present?: boolean;
  persons?: unknown[] | string | null;
  meta?: Record<string, unknown> | string | null;
}

export interface DeviceUsage {
  deviceId: string;
  timezone: string;
  date: string;
  generatedAt: string;
  hourlyMinutes: number[];
  totalMinutes: number;
  peakHour: number | null;
  averageConfidence: number | null;
  sampleCount: number;
}

export interface PhotoRequest {
  requestId?: string;
  id?: string;
  deviceId: string;
  stat: string;
  reason?: string | null;
  capturedAt?: string | null;
  createdAt?: string;
  errorMessage?: string | null;
}
