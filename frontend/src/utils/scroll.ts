export function scrollToLatest(
  element: Pick<HTMLElement, "scrollLeft" | "scrollWidth"> | null | undefined,
) {
  if (!element) return;
  element.scrollLeft = element.scrollWidth;
}
