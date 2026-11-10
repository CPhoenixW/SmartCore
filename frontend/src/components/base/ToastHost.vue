<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { X } from "@lucide/vue";
import { useI18n } from "vue-i18n";
import { useToast } from "@/composables/useToast";
import { useAppReload } from "@/composables/useAppReload";

const { messages } = useToast();
const { t } = useI18n();
const { blocked, reload } = useAppReload();
const updateAvailable = ref(false);
let announced = false;
let serviceWorker: ServiceWorkerContainer | undefined;

function onWorkerMessage(event: MessageEvent): void {
  if (announced || event.data?.shellUpdated !== true) return;
  announced = true;
  updateAvailable.value = true;
}
onMounted(() => {
  serviceWorker = navigator.serviceWorker;
  serviceWorker?.addEventListener("message", onWorkerMessage);
});
onBeforeUnmount(() => serviceWorker?.removeEventListener("message", onWorkerMessage));
</script>

<template>
  <div class="toast-host" aria-live="polite"><div v-for="item in messages" :key="item.id" class="toast" :class="`toast--${item.kind}`">{{ item.text }}</div></div>
  <aside v-if="updateAvailable" class="update-toast" role="status" aria-live="polite">
    <span>{{ t("app.updateAvailable") }}</span>
    <button class="update-toast__refresh" type="button" :disabled="blocked" @click="reload">{{ t("common.refresh") }}</button>
    <button class="update-toast__dismiss" type="button" :aria-label="t('app.updateLater')" @click="updateAvailable = false"><X :size="16" aria-hidden="true" /></button>
    <small v-if="blocked">{{ t("app.updateWhenReady") }}</small>
  </aside>
</template>

<style scoped>
.update-toast {
  position: fixed;
  top: calc(80px + env(safe-area-inset-top, 0px));
  right: 16px;
  z-index: 100;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 6px 10px;
  width: min(360px, calc(100% - 24px));
  padding: 10px 12px;
  border: 1px solid #dce3eb;
  border-radius: 12px;
  background: #fff;
  color: #334155;
  font-size: 13px;
  box-shadow: 0 5px 20px rgb(15 23 42 / 12%);
}
.update-toast button { min-height: 32px; border: 0; border-radius: 8px; font: inherit; }
.update-toast__refresh { padding: 5px 11px; background: #334155; color: #fff; }
.update-toast__refresh:disabled { background: #e2e8f0; color: #64748b; cursor: not-allowed; }
.update-toast__dismiss { display: grid; place-items: center; width: 30px; padding: 0; background: transparent; color: #64748b; }
.update-toast small { grid-column: 1 / -1; color: #64748b; font-size: 11px; line-height: 1.4; }
@media (max-width: 760px) { .update-toast { top: calc(64px + env(safe-area-inset-top, 0px)); right: 12px; } }
</style>
