import { enableAutoUnmount, flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ToastHost from "@/components/base/ToastHost.vue";
import { useAppReload } from "@/composables/useAppReload";
import { i18n } from "@/locales";

const { reloadMock } = vi.hoisted(() => ({ reloadMock: vi.fn() }));
vi.mock("@/composables/useAppReload", async () => {
  const { ref } = await import("vue");
  const blocked = ref(false);
  return { useAppReload: () => ({ blocked, reload: reloadMock }) };
});

enableAutoUnmount(afterEach);
afterEach(() => vi.unstubAllGlobals());
let worker: EventTarget;
beforeEach(() => {
  worker = new EventTarget();
  vi.stubGlobal("navigator", { serviceWorker: worker });
  useAppReload().blocked.value = false;
  reloadMock.mockReset();
});
function signal(data: unknown) { worker.dispatchEvent(new MessageEvent("message", { data })); }
function render() { return mount(ToastHost, { attachTo: document.body, global: { plugins: [i18n] } }); }

describe("workbench update notice", () => {
  it("appears only for a shell update, leaves focus alone, and stays dismissed", async () => {
    const wrapper = render();
    const draft = document.createElement("textarea");
    document.body.append(draft);
    draft.value = "未发送的草稿";
    draft.focus();
    expect(wrapper.find(".update-toast").exists()).toBe(false);
    signal({ shellUpdated: false });
    await flushPromises();
    expect(wrapper.find(".update-toast").exists()).toBe(false);
    signal({ shellUpdated: true });
    await flushPromises();
    expect(wrapper.get(".update-toast").text()).toContain("有新版本可用");
    expect(document.activeElement).toBe(draft);
    expect(draft.value).toBe("未发送的草稿");
    expect(reloadMock).not.toHaveBeenCalled();
    await wrapper.get(".update-toast__dismiss").trigger("click");
    signal({ shellUpdated: true });
    await flushPromises();
    expect(wrapper.find(".update-toast").exists()).toBe(false);
    draft.remove();
  });

  it("does not allow refresh during a draft or reply and waits for an explicit click", async () => {
    useAppReload().blocked.value = true;
    const wrapper = render();
    signal({ shellUpdated: true });
    await flushPromises();
    expect(wrapper.get(".update-toast__refresh").attributes("disabled")).toBeDefined();
    await wrapper.get(".update-toast__refresh").trigger("click");
    expect(reloadMock).not.toHaveBeenCalled();
    useAppReload().blocked.value = false;
    await flushPromises();
    expect(wrapper.get(".update-toast__refresh").attributes("disabled")).toBeUndefined();
    expect(reloadMock).not.toHaveBeenCalled();
    await wrapper.get(".update-toast__refresh").trigger("click");
    expect(reloadMock).toHaveBeenCalledOnce();
  });

  it("removes its listener on unmount and works without a service worker", () => {
    const remove = vi.spyOn(worker, "removeEventListener");
    const wrapper = render();
    wrapper.unmount();
    expect(remove).toHaveBeenCalledWith("message", expect.any(Function));
    vi.stubGlobal("navigator", {});
    expect(render().find(".update-toast").exists()).toBe(false);
  });
});
