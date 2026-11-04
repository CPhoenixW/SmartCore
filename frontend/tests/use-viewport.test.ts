import { defineComponent, nextTick } from "vue";
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useViewport } from "@/composables/useViewport";

describe("useViewport", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("tracks the 760px workbench breakpoint", async () => {
    const listeners = new Set<(event: MediaQueryListEvent) => void>();
    const media = {
      matches: true,
      addEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => {
        listeners.add(listener);
      },
      removeEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => {
        listeners.delete(listener);
      },
    };
    vi.stubGlobal("matchMedia", vi.fn(() => media));

    const Host = defineComponent({
      setup() {
        return useViewport();
      },
      template: "<span>{{ isMobile }}</span>",
    });
    const wrapper = mount(Host);
    await nextTick();
    expect(wrapper.text()).toBe("true");

    media.matches = false;
    for (const listener of listeners) listener({ matches: false } as MediaQueryListEvent);
    await nextTick();
    expect(wrapper.text()).toBe("false");
    wrapper.unmount();
  });
});
