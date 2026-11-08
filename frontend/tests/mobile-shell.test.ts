import { defineComponent, nextTick } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@/locales";

vi.mock("@tanstack/vue-query", () => ({
  useQuery: () => ({ data: { value: [] }, isPending: { value: false }, isError: { value: false }, refetch: vi.fn() }),
  useMutation: () => ({ mutate: vi.fn(), isPending: { value: false } }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));
vi.mock("@/api/auth", () => ({
  authApi: { logout: vi.fn().mockResolvedValue(undefined), sessions: vi.fn(), logoutAll: vi.fn(), changePassword: vi.fn(), revokeSession: vi.fn() },
}));

function stubViewport(mobile: boolean) {
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: mobile, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
}

const Blank = defineComponent({ template: "<div />" });
function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: ["overview", "assistant", "notifications", "settings", "memory", "schedule", "add", "update", "course", "dailySummary", "device", "ideas", "logs", "login"].map(
      (name) => ({ path: `/${name}`, name, component: Blank }),
    ),
  });
}

describe("mobile shell", () => {
  beforeEach(() => setActivePinia(createPinia()));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("phone layout opens the left drawer from the top-left menu", async () => {
    stubViewport(true);
    const { default: WorkLayout } = await import("@/layouts/WorkLayout.vue");
    const router = makeRouter();
    await router.push("/overview");
    const wrapper = mount(WorkLayout, { global: { plugins: [i18n, router] } });
    await nextTick();
    expect(wrapper.find(".mobile-tabbar").exists()).toBe(false);
    expect(wrapper.find(".sidebar").exists()).toBe(true);
    expect(wrapper.find(".sidebar--mobile").exists()).toBe(true);
    expect(wrapper.find(".mobile-menu").exists()).toBe(true);
    expect(wrapper.find(".notification-button").attributes("href")).toContain("/notifications");
  });

  it("desktop layout keeps the sidebar and has no tab bar", async () => {
    stubViewport(false);
    const { default: WorkLayout } = await import("@/layouts/WorkLayout.vue");
    const router = makeRouter();
    await router.push("/overview");
    const wrapper = mount(WorkLayout, { global: { plugins: [i18n, router] } });
    await nextTick();
    expect(wrapper.find(".mobile-tabbar").exists()).toBe(false);
    expect(wrapper.find(".sidebar").exists()).toBe(true);
    expect(wrapper.findAll(".sidebar .nav-list a").map((a) => a.text())).toEqual(["助手", "总览", "通知", "设置"]);
  });

  it("phone overview merges the schedule into one column", async () => {
    stubViewport(true);
    const { default: OverviewView } = await import("@/views/OverviewView.vue");
    const wrapper = mount(OverviewView, { global: { plugins: [i18n, makeRouter()] } });
    await nextTick();
    expect(wrapper.find(".m-overview").exists()).toBe(true);
    expect(wrapper.find(".overview-columns").exists()).toBe(false);
    expect(wrapper.text()).toContain("今日安排");
    expect(wrapper.text()).not.toContain("今天剩下");
    expect(wrapper.find(".natural-input").exists()).toBe(false);
  });

  it("phone settings keeps only everyday items", async () => {
    stubViewport(true);
    const { default: SettingsView } = await import("@/views/SettingsView.vue");
    const wrapper = mount(SettingsView, { global: { plugins: [i18n, makeRouter()] } });
    await flushPromises();
    expect(wrapper.find(".m-settings").exists()).toBe(true);
    expect(wrapper.find(".settings-scroll-layout").exists()).toBe(false);
    const text = wrapper.text();
    expect(text).not.toContain("记忆");
    expect(text).toContain("退出登录");
    for (const removed of ["修改密码", "浏览器会话", "头像 URL", "每日总结", "灵感", "日志"]) expect(text).not.toContain(removed);
  });
});
