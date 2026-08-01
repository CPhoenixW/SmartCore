import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import {
  STAGED_WHEEL_WINDOW_MS,
  bindStagedWheelScroll,
} from "@/utils/scroll";

function createScrollWindow(scrollTop = 0) {
  const root = document.createElement("main");
  const windowElement = document.createElement("section");
  const child = document.createElement("div");
  windowElement.dataset.stagedWheelScroll = "";
  windowElement.append(child);
  root.append(windowElement);
  document.body.append(root);
  Object.defineProperties(windowElement, {
    clientHeight: { configurable: true, value: 100 },
    scrollHeight: { configurable: true, value: 400 },
    scrollTop: { configurable: true, value: scrollTop, writable: true },
  });
  return { child, root, windowElement };
}

function wheel(target: Element, deltaY: number, deltaX = 0) {
  const event = new WheelEvent("wheel", {
    bubbles: true,
    cancelable: true,
    deltaX,
    deltaY,
  });
  target.dispatchEvent(event);
  return event;
}

describe("staged wheel scrolling", () => {
  it("scrolls the page first, then the inner window on a quick second step", () => {
    const { child, root, windowElement } = createScrollWindow();
    const pageScroll = vi.fn();
    let time = 1_000;
    const unbind = bindStagedWheelScroll(root, { now: () => time, scrollPage: pageScroll });

    const first = wheel(child, 48);
    expect(first.defaultPrevented).toBe(true);
    expect(pageScroll).toHaveBeenCalledWith(48);
    expect(windowElement.scrollTop).toBe(0);

    time += 120;
    const second = wheel(child, 48);
    expect(second.defaultPrevented).toBe(true);
    expect(pageScroll).toHaveBeenCalledTimes(1);
    expect(windowElement.scrollTop).toBe(48);

    unbind();
    root.remove();
  });

  it("requires a new first step after the timeout or a direction change", () => {
    const { child, root, windowElement } = createScrollWindow(100);
    const pageScroll = vi.fn();
    let time = 2_000;
    const unbind = bindStagedWheelScroll(root, { now: () => time, scrollPage: pageScroll });

    wheel(child, 30);
    time += STAGED_WHEEL_WINDOW_MS + 1;
    wheel(child, 30);
    expect(windowElement.scrollTop).toBe(100);
    expect(pageScroll).toHaveBeenCalledTimes(2);

    time += 20;
    wheel(child, -30);
    expect(windowElement.scrollTop).toBe(100);
    expect(pageScroll).toHaveBeenLastCalledWith(-30);

    time += 20;
    wheel(child, -30);
    expect(windowElement.scrollTop).toBe(70);

    unbind();
    root.remove();
  });

  it("returns wheel control to the page at either inner boundary", () => {
    const down = createScrollWindow(300);
    const downPageScroll = vi.fn();
    const unbindDown = bindStagedWheelScroll(down.root, { scrollPage: downPageScroll });
    wheel(down.child, 40);
    wheel(down.child, 40);
    expect(down.windowElement.scrollTop).toBe(300);
    expect(downPageScroll).toHaveBeenCalledTimes(2);

    const up = createScrollWindow(0);
    const upPageScroll = vi.fn();
    const unbindUp = bindStagedWheelScroll(up.root, { scrollPage: upPageScroll });
    wheel(up.child, -40);
    expect(up.windowElement.scrollTop).toBe(0);
    expect(upPageScroll).toHaveBeenCalledWith(-40);

    unbindDown();
    unbindUp();
    down.root.remove();
    up.root.remove();
  });

  it("keeps state independent for each window", () => {
    const root = document.createElement("main");
    const first = createScrollWindow();
    const second = createScrollWindow();
    root.append(first.windowElement, second.windowElement);
    document.body.append(root);
    first.root.remove();
    second.root.remove();
    const pageScroll = vi.fn();
    let time = 3_000;
    const unbind = bindStagedWheelScroll(root, { now: () => time, scrollPage: pageScroll });

    wheel(first.child, 25);
    time += 50;
    wheel(second.child, 25);
    expect(first.windowElement.scrollTop).toBe(0);
    expect(second.windowElement.scrollTop).toBe(0);

    time += 50;
    wheel(first.child, 25);
    expect(first.windowElement.scrollTop).toBe(25);
    expect(second.windowElement.scrollTop).toBe(0);

    unbind();
    root.remove();
  });

  it("does not intercept horizontal gestures, form controls, or events after cleanup", () => {
    const { child, root, windowElement } = createScrollWindow();
    const input = document.createElement("textarea");
    windowElement.append(input);
    const pageScroll = vi.fn();
    const unbind = bindStagedWheelScroll(root, { scrollPage: pageScroll });

    expect(wheel(child, 10, 50).defaultPrevented).toBe(false);
    expect(wheel(input, 30).defaultPrevented).toBe(false);
    unbind();
    expect(wheel(child, 30).defaultPrevented).toBe(false);
    expect(pageScroll).not.toHaveBeenCalled();

    root.remove();
  });
});

describe("staged scroll window coverage", () => {
  it("marks every split column and the remaining fixed-height vertical windows", () => {
    for (const view of ["CourseView.vue", "IdeaView.vue", "AddEventView.vue", "UpdateEventView.vue"]) {
      const source = readFileSync(resolve(process.cwd(), `src/views/${view}`), "utf8");
      const splitColumns = source.match(/<(?:div|aside)[^>]*class="[^"]*split-scroll-column[^"]*"[^>]*>/g) ?? [];
      expect(splitColumns).toHaveLength(2);
      expect(splitColumns.every((tag) => tag.includes("data-staged-wheel-scroll"))).toBe(true);
    }

    const cases = [
      ["src/views/OverviewView.vue", 2],
      ["src/views/SettingsView.vue", 2],
      ["src/views/RaspberryPiView.vue", 2],
      ["src/components/device/ComputerUsagePanel.vue", 2],
      ["src/components/device/DevicePairPanel.vue", 1],
    ] as const;
    for (const [path, count] of cases) {
      const source = readFileSync(resolve(process.cwd(), path), "utf8");
      expect(source.match(/data-staged-wheel-scroll/g)).toHaveLength(count);
    }

    const layout = readFileSync(resolve(process.cwd(), "src/layouts/WorkLayout.vue"), "utf8");
    expect(layout).toContain("bindStagedWheelScroll(pageRoot.value)");
  });
});
