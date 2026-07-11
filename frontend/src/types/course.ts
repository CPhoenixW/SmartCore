import type { Priority } from "./event";

export interface CoursePayload {
  title?: string;
  courseName: string;
  teacher?: string | null;
  location?: string | null;
  semesterStart: string;
  weekDay: number;
  startWeek: number;
  endWeek: number;
  weekMode: "all" | "odd" | "even";
  stTime: string;
  endTime: string;
  desc?: string | null;
  prio: Priority;
}
