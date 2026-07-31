import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import UpdateEventView from "@/views/UpdateEventView.vue";
import { i18n } from "@/locales";
import type { SmartCoreEvent } from "@/types/event";

const { events, readMock, replaceMock } = vi.hoisted(() => ({
  events: [
    {
      evtId: "event-1",
      title: "First event",
      evtType: "plan",
      stat: "todo",
      prio: "mid",
      stTime: "2026-07-31T09:00:00+08:00",
      durationMin: 30,
    },
    {
      evtId: "event-2",
      title: "Second event",
      evtType: "plan",
      stat: "todo",
      prio: "mid",
      stTime: "2026-07-31T10:00:00+08:00",
      durationMin: 30,
    },
  ] as SmartCoreEvent[],
  readMock: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("vue-router", () => ({
  useRoute: () => ({ query: { date: "2026-07-31" } }),
  useRouter: () => ({ replace: replaceMock }),
}));

vi.mock("@tanstack/vue-query", () => ({
  useQuery: () => ({ data: { value: events }, isPending: { value: false } }),
  useMutation: () => ({ mutate: vi.fn(), isPending: { value: false } }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/api/event", () => ({
  eventApi: {
    list: vi.fn(),
    read: readMock,
    update: vi.fn(),
    cancel: vi.fn(),
  },
}));

describe("UpdateEventView", () => {
  it("previews the first filtered event by default", async () => {
    readMock.mockImplementation(async (id: string) => events.find((event) => event.evtId === id));

    const wrapper = mount(UpdateEventView, { global: { plugins: [i18n] } });
    await flushPromises();

    expect(readMock).toHaveBeenCalledTimes(1);
    expect(readMock).toHaveBeenCalledWith("event-1");
    expect(wrapper.get(".event-card--selected").text()).toContain("First event");
    expect(wrapper.get(".event-detail-preview").text()).toContain("First event");
  });
});
