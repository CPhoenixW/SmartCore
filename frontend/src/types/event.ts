export type EventStatus = "todo" | "done" | "cancelled";
export type Priority = "low" | "mid" | "high";
export type EventType = "plan" | "remind" | "ddl" | "course";

export interface BaseEvent {
  evtId: string;
  title: string;
  desc?: string | null;
  evtType: EventType;
  stat: EventStatus;
  prio: Priority;
  createdAt?: string;
  updatedAt?: string;
}

export interface ReminderSummary {
  evtId: string;
  triggerTime: string;
  remindKind?: string | null;
  stat?: EventStatus;
  firedAt?: string | null;
}

export interface PlanEvent extends BaseEvent {
  evtType: "plan";
  stTime: string;
  durationMin: number;
  reminders?: ReminderSummary[];
  generatedBy?: "course" | "ddl" | null;
  courseEvtId?: string | null;
  ddlEvtId?: string | null;
  occurrenceDate?: string | null;
  sequenceNo?: number | null;
  courseName?: string | null;
  planRole?: DdlPlan["planRole"];
  sortOrder?: number | null;
}

export interface ReminderEvent extends BaseEvent {
  evtType: "remind";
  triggerTime: string;
  planEvtId?: string | null;
  ddlEvtId?: string | null;
  remindKind?: string | null;
  offsetMin?: number | null;
  firedAt?: string | null;
}

export interface DdlPlan {
  planEvtId?: string;
  evtId?: string;
  planRole: "one_day_before" | "one_hour_before" | "manual";
  title?: string | null;
  desc?: string | null;
  stTime: string;
  durationMin: number;
  enabled?: boolean;
  sortOrder?: number;
}

export interface DdlReminder {
  remindEvtId?: string;
  evtId?: string;
  title?: string | null;
  desc?: string | null;
  triggerTime: string;
  prio?: Priority;
  enabled?: boolean;
}

export interface DdlEvent extends BaseEvent {
  evtType: "ddl";
  endTime: string;
  hardDdl: boolean;
  plans: DdlPlan[];
  ddlReminders: DdlReminder[];
}

export interface CourseEvent extends BaseEvent {
  evtType: "course";
  courseName: string;
  teacher?: string | null;
  location?: string | null;
  semesterStart?: string;
  computedEndDate?: string;
  stDate?: string;
  endDate?: string;
  weekDay: number;
  startWeek: number;
  endWeek: number;
  weekMode: "all" | "odd" | "even";
  stTime: string;
  endTime: string;
  occurrenceCount?: number;
  nextOccurrence?: PlanEvent | null;
  plans?: PlanEvent[];
}

export type SmartCoreEvent = PlanEvent | ReminderEvent | DdlEvent | CourseEvent;

export interface EventQuery {
  date?: string;
  evtType?: EventType[];
  stat?: EventStatus[];
  text?: string;
  includeReminders?: boolean;
  includeCourseTemplates?: boolean;
}

export interface CreatePlanPayload {
  title: string;
  desc?: string | null;
  stTime: string;
  durationMin: number;
  prio: Priority;
}

export interface CreateReminderPayload {
  title: string;
  desc?: string | null;
  triggerTime: string;
  prio: Priority;
}

export interface CreateDdlPayload {
  title: string;
  desc?: string | null;
  endTime: string;
  hardDdl: boolean;
  prio: Priority;
  plans: DdlPlan[];
  ddlReminders: DdlReminder[];
}

export type UpdateEventPayload = Record<string, unknown>;
