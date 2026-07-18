export interface DevicePerson {
  personId?: string | null;
  name?: string | null;
  confidence?: number | null;
  [key: string]: unknown;
}

export interface DeviceMeta {
  present?: boolean;
  persons?: DevicePerson[];
  clockSkewSeconds?: number;
  model?: string;
  camera?: string;
  reportedAt?: string;
  receivedAt?: string;
  [key: string]: unknown;
}

export interface DeviceState {
  stateLogId?: string;
  deviceId: string;
  state: "working" | "away" | "offline" | "unknown" | string;
  confidence?: number | null;
  seenAt: string;
  meta?: DeviceMeta | string | null;
}

export interface DeviceStateView {
  state: string;
  label: string;
  stale: boolean;
  seenAt: string | null;
  confidence: number | null;
  present: boolean;
  persons: DevicePerson[];
  meta: DeviceMeta;
}

export interface DeviceUsagePoint {
  startAt: string;
  endAt: string;
  minutes: number;
}

export interface DeviceUsage {
  deviceId: string;
  timezone: string;
  windowStart: string;
  windowEnd: string;
  generatedAt: string;
  points: DeviceUsagePoint[];
  rangeHours: number;
  totalMinutes: number;
  peakStartAt: string | null;
  averageConfidence: number | null;
  sampleCount: number;
}

export interface PhotoRequest {
  requestId: string;
  deviceId: string;
  stat: "pending" | "uploaded" | "failed" | "expired" | "cancelled" | string;
  reason?: string | null;
  requestedAt?: string | null;
  expiresAt?: string | null;
  dispatchedAt?: string | null;
  capturedAt?: string | null;
  completedAt?: string | null;
  mimeType?: string | null;
  imageSize?: number | null;
  recognition?: Record<string, unknown> | null;
  errorMessage?: string | null;
  imageAvailable?: boolean;
  imageUrl?: string | null;
}
