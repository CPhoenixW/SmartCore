<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import DevicePairPanel from "@/components/device/DevicePairPanel.vue";
import DeviceManagementPanel from "@/components/device/DeviceManagementPanel.vue";
import { deviceRegistryApi } from "@/api/deviceRegistry";
import { eventApi } from "@/api/event";
import type { PlanEvent } from "@/types/event";
import { formatDateTime, todayKey } from "@/utils/date";

const { t } = useI18n();
const previewFrame = ref<HTMLIFrameElement | null>(null);
const devices = useQuery({ queryKey: ["lifeDevices"], queryFn: deviceRegistryApi.list, refetchInterval: 15_000 });
const events = useQuery({ queryKey: ["screenPlans", todayKey()], queryFn: () => eventApi.list({ date: todayKey(), evtType: ["plan"], stat: ["todo"] }), refetchInterval: 60_000 });
const screens = computed(() => (devices.data.value ?? []).filter((item) => item.deviceKind === "screen"));
const lastSeenAt = computed(() => {
  const values = screens.value.map((item) => item.lastSeenAt).filter((value): value is string => Boolean(value)).sort();
  return values[values.length - 1] ?? null;
});
const plans = computed(() => (events.data.value ?? []).filter((item): item is PlanEvent => item.evtType === "plan").sort((left, right) => left.stTime.localeCompare(right.stTime)));
const currentPlan = computed(() => {
  const now = Date.now();
  return plans.value.find((plan) => {
    const start = new Date(plan.stTime).getTime();
    return start <= now && start + plan.durationMin * 60_000 > now;
  }) ?? null;
});
function updateScreenPreview() {
  previewFrame.value?.contentWindow?.postMessage({
    kind: "smartcore-screen-preview",
    events: plans.value,
    state: currentPlan.value ? "working" : "away",
  }, window.location.origin);
}
watch([plans, currentPlan], updateScreenPreview, { flush: "post" });
</script>

<template>
  <div class="device-data-page">
    <section class="screen-overview">
      <BaseCard :title="t('screenDevice.displaySchedule')">
        <template #actions>
          <div class="screen-preview-status">
            <span>{{ t("screenDevice.registered") }} <strong>{{ screens.length }}</strong></span>
            <span>{{ t("screenDevice.lastConnection") }} <strong>{{ lastSeenAt ? formatDateTime(lastSeenAt) : t("pair.notReported") }}</strong></span>
          </div>
        </template>
        <div class="screen-live-preview">
          <iframe ref="previewFrame" src="/screen?preview=1" :title="t('screenDevice.previewTitle')" tabindex="-1" @load="updateScreenPreview" />
        </div>
      </BaseCard>
    </section>
    <DeviceManagementPanel icon="SC" :title="t('screenDevice.managementTitle')" :summary="t('screenDevice.managementSummary', { count: screens.length })"><DevicePairPanel embedded :allowed-kinds="['screen']" :title="t('screenDevice.pairTitle')" /></DeviceManagementPanel>
  </div>
</template>
