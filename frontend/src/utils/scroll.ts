export function scrollToLatest(
  element: Pick<HTMLElement, "scrollLeft" | "scrollWidth"> | null | undefined,
) {
  if (!element) return;
  element.scrollLeft = element.scrollWidth;
}

export const STAGED_WHEEL_SELECTOR = "[data-staged-wheel-scroll]";
export const STAGED_WHEEL_WINDOW_MS = 500;

interface StagedWheelState {
  direction: -1 | 1;
  at: number;
}

export interface StagedWheelScrollOptions {
  activationWindowMs?: number;
  now?: () => number;
  scrollPage?: (deltaY: number) => void;
}

function normalizedWheelDelta(event: WheelEvent, element: HTMLElement) {
  if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) return event.deltaY * 16;
  if (event.deltaMode === WheelEvent.DOM_DELTA_PAGE) return event.deltaY * element.clientHeight;
  return event.deltaY;
}

function canScroll(element: HTMLElement, direction: -1 | 1) {
  if (element.scrollHeight <= element.clientHeight + 1) return false;
  if (direction > 0) return element.scrollTop + element.clientHeight < element.scrollHeight - 1;
  return element.scrollTop > 1;
}

function isNativeWheelTarget(target: Element) {
  return Boolean(target.closest("textarea, input, select, [contenteditable='true'], [data-native-wheel-scroll]"));
}

/**
 * Gives the page the first vertical wheel step over a marked scroll window.
 * A second step in the same direction within the activation window scrolls
 * that inner window. Reaching an inner boundary immediately returns control
 * to the page. Horizontal gestures and native form controls are untouched.
 */
export function bindStagedWheelScroll(
  root: HTMLElement,
  options: StagedWheelScrollOptions = {},
) {
  const states = new WeakMap<HTMLElement, StagedWheelState>();
  const activationWindowMs = options.activationWindowMs ?? STAGED_WHEEL_WINDOW_MS;
  const now = options.now ?? Date.now;
  const scrollPage = options.scrollPage ?? ((deltaY: number) => {
    root.ownerDocument.defaultView?.scrollBy({ top: deltaY, left: 0, behavior: "auto" });
  });

  const onWheel = (event: WheelEvent) => {
    if (
      event.ctrlKey
      || event.shiftKey
      || event.deltaY === 0
      || Math.abs(event.deltaX) >= Math.abs(event.deltaY)
    ) return;

    const target = event.target;
    if (!(target instanceof Element) || isNativeWheelTarget(target)) return;
    const element = target.closest<HTMLElement>(STAGED_WHEEL_SELECTOR);
    if (!element || !root.contains(element)) return;

    const deltaY = normalizedWheelDelta(event, element);
    const direction: -1 | 1 = deltaY > 0 ? 1 : -1;
    if (!canScroll(element, direction)) {
      states.delete(element);
      event.preventDefault();
      scrollPage(deltaY);
      return;
    }

    const currentTime = now();
    const previous = states.get(element);
    const isSecondStep = Boolean(
      previous
      && previous.direction === direction
      && currentTime - previous.at <= activationWindowMs,
    );
    states.set(element, { direction, at: currentTime });
    event.preventDefault();

    if (isSecondStep) {
      element.scrollTop += deltaY;
      return;
    }
    scrollPage(deltaY);
  };

  root.addEventListener("wheel", onWheel, { passive: false });
  return () => root.removeEventListener("wheel", onWheel);
}
