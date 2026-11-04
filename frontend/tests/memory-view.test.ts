import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import MemoryView from "@/views/MemoryView.vue";
import { memoryApi } from "@/api/memory";
import { i18n } from "@/locales";

const { listData } = vi.hoisted(() => ({
  listData: {
    enabled: true,
    items: [
      {
        memoryId: "m1",
        type: "preference" as const,
        typeLabel: "偏好",
        content: "用户喜欢早上处理难的任务",
        source: "user_explicit" as const,
        confidence: 1,
        createdAt: "2026-11-04T16:00:00+08:00",
        updatedAt: "2026-11-04T16:00:00+08:00",
        lastUsedAt: null,
        expiresAt: null,
      },
      {
        memoryId: "m2",
        type: "profile" as const,
        typeLabel: "个人信息",
        content: "用户在读研究生",
        source: "auto_extracted" as const,
        confidence: 0.8,
        createdAt: "2026-11-04T16:00:00+08:00",
        updatedAt: "2026-11-04T16:00:00+08:00",
        lastUsedAt: "2026-11-04T16:05:00+08:00",
        expiresAt: null,
      },
    ],
    types: [],
  },
}));

vi.mock("@tanstack/vue-query", () => ({
  useQuery: () => ({ data: { value: listData }, isPending: { value: false }, refetch: vi.fn() }),
  useMutation: (options: { mutationFn: (arg?: unknown) => Promise<unknown>; onSuccess?: () => void }) => ({
    mutate: vi.fn(async (arg?: unknown) => {
      await options.mutationFn(arg);
      options.onSuccess?.();
    }),
    isPending: { value: false },
  }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/api/memory", () => ({
  memoryApi: {
    list: vi.fn(),
    create: vi.fn().mockResolvedValue({}),
    update: vi.fn().mockResolvedValue({}),
    remove: vi.fn().mockResolvedValue({ memoryId: "m1", deleted: true }),
  },
}));

describe("MemoryView", () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it("lists memories in Chinese and filters by type", async () => {
    const wrapper = mount(MemoryView, { global: { plugins: [i18n] } });
    expect(wrapper.text()).toContain("用户喜欢早上处理难的任务");
    expect(wrapper.text()).toContain("你告诉我的");
    expect(wrapper.findAll(".memory-item")).toHaveLength(2);

    const profileTab = wrapper.findAll(".memory-filters .tab").find((tab) => tab.text() === "个人信息");
    await profileTab!.trigger("click");
    expect(wrapper.findAll(".memory-item")).toHaveLength(1);
    expect(wrapper.text()).toContain("用户在读研究生");
  });

  it("adds, edits and deletes a memory", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true));
    const wrapper = mount(MemoryView, { global: { plugins: [i18n] } });

    await wrapper.get(".memory-form input").setValue("我对花生过敏");
    await wrapper.get(".memory-form").trigger("submit");
    expect(memoryApi.create).toHaveBeenCalledWith({ content: "我对花生过敏", type: undefined });

    await wrapper.findAll(".memory-item")[0]!.findAll("button")[0]!.trigger("click");
    await wrapper.get(".memory-edit input").setValue("用户喜欢上午处理难的任务");
    await wrapper.get(".memory-edit").trigger("submit");
    expect(memoryApi.update).toHaveBeenCalledWith("m1", { content: "用户喜欢上午处理难的任务", type: "preference" });
    await flushPromises();

    await wrapper.findAll(".memory-item")[0]!.find(".button--danger").trigger("click");
    expect(memoryApi.remove).toHaveBeenCalledWith("m1");
  });
});
