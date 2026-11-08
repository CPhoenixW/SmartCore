import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import OverviewView from "@/views/OverviewView.vue";
import { i18n } from "@/locales";

const { queryValues } = vi.hoisted(() => ({ queryValues: [] as unknown[] }));

vi.mock("@tanstack/vue-query", () => ({
  useQuery: () => ({
    data: { value: queryValues.shift() ?? [] },
    isPending: { value: false },
    isError: { value: false },
  }),
  useMutation: () => ({ mutate: vi.fn(), isPending: { value: false } }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/components/overview/NotificationInbox.vue", () => ({
  default: { template: "<div class=\"notification-inbox-stub\" />" },
}));

const clock = { serverNow: "2026-07-31T08:00:00+08:00", timezone: "Asia/Shanghai" };

function plan(evtId: string, title: string, stTime: string, durationMin: number, stat: "todo" | "done" = "todo") {
  return { evtId, title, desc: "", evtType: "plan", stat, prio: "mid", stTime, durationMin };
}

function mountOverview(): ReturnType<typeof mount> {
  return mount(OverviewView, {
    global: {
      plugins: [i18n],
      mocks: { $router: { push: vi.fn() } },
      stubs: { RouterLink: true },
    },
  });
}

describe("OverviewView", () => {
  beforeEach(() => {
    queryValues.splice(0, queryValues.length, clock, [], [], []);
  });

  it("keeps the overview focused on actions", () => {
    const wrapper = mountOverview();

    expect(wrapper.find(".overview-focus").exists()).toBe(true);
    expect(wrapper.find(".overview-assistant").exists()).toBe(false);
    expect(wrapper.find(".global-search").exists()).toBe(false);
    expect(wrapper.text()).toContain("下一项行动");
  });

  it("shows the current action before the next action and colours completed rows", () => {
    const current = plan("current", "正在写报告", "2026-07-31T10:00:00+08:00", 90);
    const completed = plan("done", "晨间计划", "2026-07-31T08:30:00+08:00", 30, "done");
    const next = plan("next", "午后复盘", "2026-07-31T13:00:00+08:00", 45);
    queryValues.splice(0, queryValues.length, { ...clock, serverNow: "2026-07-31T10:30:00+08:00" }, [current, completed], [current, completed, next], []);

    const wrapper = mountOverview();

    expect(wrapper.find(".overview-focus__action--current").exists()).toBe(true);
    expect(wrapper.find(".overview-focus__action").text()).toContain("当前行动");
    expect(wrapper.find(".overview-focus__action").text()).toContain("正在写报告");
    expect(wrapper.find(".overview-event-row--current").exists()).toBe(true);
    expect(wrapper.find(".overview-event-row--done").exists()).toBe(true);
    const times = wrapper.findAll(".overview-event-row__time").map((node) => node.text());
    expect(times.some((text) => text.includes("开始 10:00") && text.includes("结束 11:30"))).toBe(true);
  });

  it("falls back to the next action from a future day", () => {
    const tomorrow = plan("tomorrow", "明日评审", "2026-08-01T09:00:00+08:00", 60);
    queryValues.splice(0, queryValues.length, clock, [], [tomorrow], []);

    const wrapper = mountOverview();

    expect(wrapper.find(".overview-focus__action").text()).toContain("下一项行动");
    expect(wrapper.find(".overview-focus__action").text()).toContain("明日评审");
  });
});
