import { enableAutoUnmount, flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import OverviewView from "@/views/OverviewView.vue";
import MobileOverview from "@/components/overview/MobileOverview.vue";
import { i18n } from "@/locales";
import type { EventQuery, PlanEvent } from "@/types/event";

const { listMock } = vi.hoisted(() => ({ listMock: vi.fn() }));
vi.mock("@/api/event", () => ({ eventApi: { list: listMock, update: vi.fn() } }));
vi.mock("@/api/runtime", () => ({ runtimeApi: { clock: vi.fn().mockResolvedValue({ serverNow: "2026-07-31T08:00:00+08:00", timezone: "Asia/Shanghai" }) } }));
vi.mock("@/api/idea", () => ({ ideaApi: { list: vi.fn().mockResolvedValue([]) } }));
vi.mock("@/composables/useViewport", async () => {
  const { ref } = await import("vue");
  return { useViewport: () => ({ isMobile: ref(false) }) };
});

enableAutoUnmount(afterEach);
const clients: QueryClient[] = [];
afterEach(() => { clients.splice(0).forEach((client) => client.clear()); });
beforeEach(() => { listMock.mockReset(); });

function plan(evtId: string, stTime: string): PlanEvent {
  return { evtId, title: evtId, evtType: "plan", stat: "todo", prio: "mid", stTime, durationMin: 30 };
}
function render(component: typeof OverviewView | typeof MobileOverview) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(queryClient);
  return mount(component, { global: { plugins: [i18n, [VueQueryPlugin, { queryClient }]], stubs: { RouterLink: true } } });
}
const futureQuery = { start: "2026-08-03T23:59:59", stat: ["todo"], includeReminders: true, includeCourseTemplates: false };

describe("overview future actions", () => {
  it("keeps the normal desktop load bounded when a near-term action exists", async () => {
    listMock.mockResolvedValue([plan("今天复习", "2026-07-31T09:00:00+08:00")]);
    render(OverviewView);
    await flushPromises();
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(listMock).toHaveBeenCalledWith({ start: "2026-07-31T00:00:00", end: "2026-08-03T23:59:59", includeReminders: true, includeCourseTemplates: false });
  });

  it("waits for the window before fetching and selecting the earliest distant action", async () => {
    let resolveWindow: ((events: PlanEvent[]) => void) | undefined;
    listMock.mockImplementation((query: EventQuery) => query.end
      ? new Promise<PlanEvent[]>((resolve) => { resolveWindow = resolve; })
      : Promise.resolve([plan("下月检查", "2026-09-01T09:00:00+08:00"), plan("下周评审", "2026-08-10T09:00:00+08:00")]));
    const wrapper = render(OverviewView);
    await flushPromises();
    expect(listMock).toHaveBeenCalledTimes(1);
    resolveWindow?.([]);
    await flushPromises();
    expect(listMock).toHaveBeenCalledTimes(2);
    expect(listMock).toHaveBeenLastCalledWith(futureQuery);
    expect(wrapper.get(".overview-focus__action").text()).toContain("下周评审");
  });

  it("does not fetch distant actions while an overnight plan is running", async () => {
    listMock.mockResolvedValue([{ ...plan("通宵实验", "2026-07-30T23:00:00+08:00"), durationMin: 600 }]);
    const wrapper = render(OverviewView);
    await flushPromises();
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(wrapper.get(".overview-focus__action--current").text()).toContain("通宵实验");
  });

  it("uses the same distant-action fallback on mobile", async () => {
    listMock.mockImplementation((query: EventQuery) => Promise.resolve(query.end ? [] : [plan("下周评审", "2026-08-10T09:00:00+08:00")]));
    const wrapper = render(MobileOverview);
    await flushPromises();
    expect(listMock).toHaveBeenCalledTimes(2);
    expect(listMock).toHaveBeenLastCalledWith(futureQuery);
    expect(wrapper.get(".m-overview__next").text()).toContain("下周评审");
  });

  it("loads the remaining future list only when the mobile later section opens", async () => {
    const nearby = plan("明日复习", "2026-08-01T09:00:00+08:00");
    listMock.mockImplementation((query: EventQuery) => Promise.resolve(query.end ? [nearby] : [nearby, plan("下周评审", "2026-08-10T09:00:00+08:00")]));
    const wrapper = render(MobileOverview);
    await flushPromises();
    expect(listMock).toHaveBeenCalledTimes(1);
    await wrapper.get(".m-overview__later > button").trigger("click");
    await flushPromises();
    expect(listMock).toHaveBeenCalledTimes(2);
    expect(listMock).toHaveBeenLastCalledWith(futureQuery);
    expect(wrapper.findAll(".m-overview__later li")).toHaveLength(2);
    expect(wrapper.get(".m-overview__later").text()).toContain("下周评审");
  });
});
