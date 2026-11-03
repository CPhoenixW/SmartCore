import { onBeforeUnmount, onMounted, ref, type Ref } from "vue";

/** Shared workbench breakpoint: matches existing @media (max-width: 760px) rules. */
export const MOBILE_MAX_WIDTH_PX = 760;

function readIsMobile(maxWidthPx: number): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia(`(max-width: ${maxWidthPx}px)`).matches;
}

export function useViewport(maxWidthPx: number = MOBILE_MAX_WIDTH_PX): { isMobile: Ref<boolean> } {
  const isMobile = ref(readIsMobile(maxWidthPx));
  let media: MediaQueryList | undefined;
  let onChange: ((event: MediaQueryListEvent) => void) | undefined;

  onMounted(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    media = window.matchMedia(`(max-width: ${maxWidthPx}px)`);
    isMobile.value = media.matches;
    onChange = (event) => {
      isMobile.value = event.matches;
    };
    media.addEventListener("change", onChange);
  });

  onBeforeUnmount(() => {
    if (media && onChange) media.removeEventListener("change", onChange);
  });

  return { isMobile };
}
