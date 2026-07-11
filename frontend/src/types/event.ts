export type EventStatus = "todo" | "done" | "cancelled";
export type Priority = "low" | "mid" | "high";

export interface BaseEvent {
  evtId: string;
  title: string;
  desc?: string | null;
  evtType: "plan" | "remind" | "ddl";
  stat: EventStatus;
  prio: Priority;
  createdAt: string;
  updatedAt: string;
}

export interface PlanEvent extends BaseEvent {
  evtType: "plan";
  stTime: string;
  durationMin: number;
  generatedBy?: "course" | "ddl" | null;
}

export interface ReminderEvent extends BaseEvent {
  evtType: "remind";
  triggerTime: string;
  standalone: true;
}

export interface DdlPlan {
  planEvtId?: string;
  planRole: "one_day_before" | "one_hour_before" | "manual";
  title?: string;
  stTime: string;
  durationMin: number;
  sortOrder?: number;
}

export interface DdlEvent extends BaseEvent {
  evtType: "ddl";
  endTime: string;
  hardDdl: boolean;
  plans: DdlPlan[];
}

export type SmartCoreEvent = PlanEvent | ReminderEvent | DdlEvent;

export function getEventPrimaryTime(event: SmartCoreEvent): string {
  switch (event.evtType) {
    case "plan":
      return event.stTime;
    case "remind":
      return event.triggerTime;
    case "ddl":
      return event.endTime;
  }
}
