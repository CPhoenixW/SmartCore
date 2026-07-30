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
  semanticAlignment?: "aligned" | "partially_aligned" | "unrelated" | "unclear";
}

export interface ComputerWorkTopic {
  name: string;
  summary: string | null;
  activeSeconds: number;
  sessionIds?: string[];
  contextIds?: string[];
  hourStarts?: string[];
  blockIds?: string[];
}

export interface ComputerWorkBlock {
  blockId: string;
  continuationOfId: string | null;
  startAt: string;
  endAt: string | null;
  status: "open" | "closed";
  topicKey: string | null;
  title: string | null;
  summary: string | null;
  progress: string | null;
  outcome: string | null;
  blocker: string | null;
  nextStep: string | null;
  activeSeconds: number;
  idleSeconds: number;
  plannedActiveSeconds: number;
  primaryApps: Array<{ bundleId: string | null; appName: string; seconds: number }>;
  planAssessments: ComputerPlanAssessment[];
  hourStarts: string[];
  generatedAt: string | null;
  updatedAt: string;
}

export interface ComputerWorkBlockAnalysisState {
  runId: string;
  triggerType: string;
  status: "queued" | "running" | "complete" | "failed";
  attemptCount: number;
  nextRetryAt: string | null;
  errorMessage: string | null;
  updatedAt: string;
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
  workBlockIds: string[];
  phase: "preview" | "final";
  previewRevision: number;
  sourceFingerprint: string | null;
  finalizedAt: string | null;
  attemptCount: number;
  lastAttemptAt: string | null;
  leaseExpiresAt: string | null;
  nextRetryAt: string | null;
  generatedAt: string | null;
  errorMessage: string | null;
}

export type ComputerCodexWorkStatus = "completed" | "partial" | "in_progress";

export interface ComputerCodexWorkReport {
  reportId: string;
  sourceTaskId: string;
  projectKey: string;
  projectName: string;
  title: string;
  summary: string;
  status: ComputerCodexWorkStatus;
  startedAt: string | null;
  endedAt: string | null;
  evidence: Record<string, unknown> | unknown[];
}

export interface ComputerProjectInvestment {
  projectKey: string;
  projectName: string;
  status: ComputerCodexWorkStatus | null;
  statusCounts: { completed: number; partial: number; inProgress: number };
  activeSeconds: number;
  plannedActiveSeconds: number;
  codexReports: ComputerCodexWorkReport[];
  workBlocks: ComputerWorkBlock[];
  plans: Array<{
    evtId: string;
    title: string;
    description: string | null;
    status: string;
    startAt: string;
    endAt: string | null;
  }>;
}

export interface ComputerProjectTotals {
  activeSeconds: number;
  plannedActiveSeconds: number;
  codexReportCount: number;
  projectCount: number;
}

export interface ComputerInsightsReport {
  deviceId: string;
  date: string;
  hours: ComputerHourlyInsight[];
  legacyHours: ComputerHourlyInsight[];
  currentBlock: ComputerWorkBlock | null;
  workBlocks: ComputerWorkBlock[];
  topics: ComputerWorkTopic[];
  planAssessments: ComputerPlanAssessment[];
  reminders: Array<{ title: string; content: string; stat: string; dedupKey: string | null }>;
  dailyLog: ComputerDailyWorkLog | null;
  analysisState: ComputerWorkBlockAnalysisState | null;
  projects: ComputerProjectInvestment[];
  projectTotals: ComputerProjectTotals;
}
