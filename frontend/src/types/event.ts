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

export interface PlanEvent extends BaseEvent {
  evtType: "plan";
  stTime: string;
  endTime?: string;
  durationMin: number;
  generatedBy?: "course" | "ddl" | null;
  parentEvtId?: string | null;
}

export interface ReminderEvent extends BaseEvent {
  evtType: "remind";
  triggerTime: string;
  standalone?: boolean;
  planEvtId?: string | null;
}

export interface DdlPlan {
  planEvtId?: string;
  planRole: "one_day_before" | "one_hour_before" | "manual";
  title?: string | null;
  desc?: string | null;
  stTime: string;
  durationMin: number;
  enabled?: boolean;
  sortOrder?: number;
}

export interface DdlEvent extends BaseEvent {
  evtType: "ddl";
  endTime: string;
  hardDdl: boolean;
  plans: DdlPlan[];
}

export interface CourseEvent extends BaseEvent {
  evtType: "course";
  courseName: string;
  teacher?: string | null;
  location?: string | null;
  semesterStart?: string;
  stDate?: string;
  endDate?: string;
  weekDay: number;
  startWeek: number;
  endWeek: number;
  weekMode: "all" | "odd" | "even";
  stTime: string;
  endTime: string;
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
}

export type UpdateEventPayload = Partial<
  Omit<SmartCoreEvent, "evtId" | "evtType" | "createdAt" | "updatedAt">
> & { plans?: DdlPlan[] };
