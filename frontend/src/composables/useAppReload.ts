import { ref } from "vue";

const blocked = ref(false);

export function useAppReload() {
  return {
    blocked,
    reload: () => { if (!blocked.value) window.location.reload(); },
  };
}
