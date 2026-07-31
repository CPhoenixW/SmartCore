import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CourseView from "@/views/CourseView.vue";
import { i18n } from "@/locales";
import type { CourseEvent } from "@/types/event";

const { courses } = vi.hoisted(() => ({ courses: [] as CourseEvent[] }));

vi.mock("@tanstack/vue-query", () => ({
  useQuery: () => ({ data: { value: courses } }),
  useMutation: () => ({ mutate: vi.fn(), isPending: { value: false } }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

function course(evtId: string, stat: CourseEvent["stat"]): CourseEvent {
  return {
    evtId,
    evtType: "course",
    title: evtId,
    courseName: evtId,
    stat,
    prio: "mid",
    semesterStart: "2026-07-27",
    weekDay: 1,
    startWeek: 1,
    endWeek: 16,
    weekMode: "all",
    stTime: "09:00",
    endTime: "10:00",
  } as CourseEvent;
}

describe("CourseView", () => {
  beforeEach(() => {
    courses.splice(0, courses.length, course("active-course", "todo"), course("cancelled-course", "cancelled"));
  });

  it("does not render cancelled courses after deletion", () => {
    const wrapper = mount(CourseView, { global: { plugins: [i18n] } });

    expect(wrapper.text()).toContain("active-course");
    expect(wrapper.text()).not.toContain("cancelled-course");
    expect(wrapper.findAll(".course-row")).toHaveLength(1);
  });
});
