export type ComputerState = "active" | "idle" | "locked" | "sleeping" | "paused" | "offline";
export type ComputerRange = "today" | "7d" | "30d";
export type ComputerUsageRange = ComputerRange | "24h";

export interface ComputerAnalysis {
  state: "unknown" | "plan_active" | "computer_active" | "at_desk_inactive" | "away" | "computer_inactive" | "computer_sleeping" | "monitor_paused";
  confidence: "high" | "medium" | "low";
  reasonCodes: string[];
  computedAt: string;
  currentPlan: { evtId: string; title: string; startAt: string; endAt: string } | null;
  presence: { deviceId: string; state: string; present: boolean | null; observedAt: string } | null;
  algorithmVersion: number;
}

export interface ComputerMonitorStatus {
  deviceId: string;
  state: ComputerState;
  reportedState: Exclude<ComputerState, "offline">;
  stateSince: string;
  observedAt: string;
  currentAppName: string | null;
  currentWindowTitle: string | null;
  appVersion: string;
  osVersion: string;
  accessibilityGranted: boolean;
  paused: boolean;
  queueDepth: number;
  lastHeartbeatAt: string;
  stale: boolean;
  analysis: ComputerAnalysis;
}

export interface ComputerContextUsage {
  contextId: string;
  bundleId: string;
  appName: string;
  windowTitle: string | null;
  contextKind: "application" | "browser" | "ide" | "document" | null;
  domain: string | null;
  workspace: string | null;
  documentName: string | null;
  titleRedacted: boolean;
  classification: null;
  seconds: number;
}

export interface ComputerTimelinePoint {
  startAt: string;
  states: Record<Exclude<ComputerState, "offline">, number>;
  dominantContext: Omit<ComputerContextUsage, "seconds"> | null;
  sessionId: string | null;
  plannedActiveSeconds: number;
}

export interface ComputerSession {
  sessionId: string;
  startAt: string;
  endAt: string;
  activeSeconds: number;
  idleSeconds: number;
  switchCount: number;
  plannedActiveSeconds: number;
  contexts: ComputerContextUsage[];
  inference: null;
}

export interface ComputerUsageReport {
  deviceId: string;
  range: ComputerUsageRange;
  timezone: string;
  windowStart: string;
  windowEnd: string;
  status: ComputerMonitorStatus | null;
  totals: Record<`${Exclude<ComputerState, "offline">}Seconds`, number> & {
    plannedActiveSeconds: number;
    switchCount: number;
  };
  timeline: ComputerTimelinePoint[];
  daily: Array<{
    date: string;
    activeSeconds: number;
    idleSeconds: number;
    lockedSeconds: number;
    sleepingSeconds: number;
    pausedSeconds: number;
    switchCount: number;
    plannedActiveSeconds: number;
  }>;
  plans: Array<{ evtId: string; title: string; startAt: string; endAt: string; activeSeconds: number }>;
  sessions: ComputerSession[];
  applications: Array<{ bundleId: string; appName: string; seconds: number }>;
  titles: ComputerContextUsage[];
}

export type ComputerPlanExecutionState = "not_started" | "partial" | "substantially_executed" | "unclear";

export interface ComputerPlanAssessment {
  evtId: string;
  state: ComputerPlanExecutionState;
  confidence: "high" | "medium" | "low";
  evidenceCodes: string[];
  note: string | null;
  title?: string;
  activeSeconds?: number;
  durationSeconds?: number;
  overlapRatio?: number;
}

export interface ComputerWorkTopic {
  name: string;
  summary: string | null;
  activeSeconds: number;
  sessionIds?: string[];
  contextIds?: string[];
  hourStarts?: string[];
}

export interface ComputerHourlyInsight {
  analysisId: string;
  deviceId: string;
  hourStart: string;
  hourEnd: string;
  status: "queued" | "running" | "complete" | "failed";
  title: string | null;
  summary: string | null;
  activeSeconds: number;
  idleSeconds: number;
  plannedActiveSeconds: number;
  planAssessments: ComputerPlanAssessment[];
  topics: ComputerWorkTopic[];
  model: string | null;
  generatedAt: string | null;
  errorMessage: string | null;
}

export interface ComputerDailyWorkLog {
  logId: string;
  logDate: string;
  status: "queued" | "running" | "complete" | "failed";
  title: string | null;
  summary: string | null;
  topics: ComputerWorkTopic[];
  planAssessments: ComputerPlanAssessment[];
  reminderSummary: Array<Record<string, unknown>>;
  generatedAt: string | null;
  errorMessage: string | null;
}

export interface ComputerInsightsReport {
  deviceId: string;
  date: string;
  hours: ComputerHourlyInsight[];
  topics: ComputerWorkTopic[];
  planAssessments: ComputerPlanAssessment[];
  reminders: Array<{ title: string; content: string; stat: string; dedupKey: string | null }>;
  dailyLog: ComputerDailyWorkLog | null;
}
