import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ImageViewer from "@/components/base/ImageViewer.vue";
import { i18n } from "@/locales";

describe("ImageViewer", () => {
  it("fits, zooms, resets and closes from the keyboard", async () => {
    const wrapper = mount(ImageViewer, {
      props: { src: "/image.jpg", alt: "Preview", fileName: "image.jpg" },
      attachTo: document.body,
      global: { plugins: [i18n] },
    });
    const viewport = wrapper.get(".image-viewer__viewport").element as HTMLElement;
    viewport.getBoundingClientRect = () => ({
      width: 600, height: 400, left: 0, top: 0, right: 600, bottom: 400, x: 0, y: 0, toJSON: () => ({}),
    });
    const image = wrapper.get("img").element as HTMLImageElement;
    Object.defineProperty(image, "naturalWidth", { value: 1200 });
    Object.defineProperty(image, "naturalHeight", { value: 800 });
    await wrapper.get("img").trigger("load");

    expect(wrapper.get("output").text()).toBe("46%");
    const zoomIn = wrapper.findAll("button").find((button) => button.text() === "+");
    await zoomIn?.trigger("click");
    expect(wrapper.get("output").text()).toBe("55%");

    await wrapper.get(".image-viewer__viewport").trigger("dblclick");
    expect(wrapper.get("output").text()).toBe("100%");

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(wrapper.emitted("close")).toHaveLength(1);
    wrapper.unmount();
  });
});
