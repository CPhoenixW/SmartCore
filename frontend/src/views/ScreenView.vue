<script setup lang="ts">
import { computed } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import PageHeader from "@/components/base/PageHeader.vue";
import DevicePairPanel from "@/components/device/DevicePairPanel.vue";
import DeviceManagementPanel from "@/components/device/DeviceManagementPanel.vue";
import DeviceMetricStrip, { type DeviceMetric } from "@/components/device/DeviceMetricStrip.vue";
import { deviceRegistryApi } from "@/api/deviceRegistry";
import { eventApi } from "@/api/event";
import type { PlanEvent } from "@/types/event";
import { formatDateTime, todayKey } from "@/utils/date";

const { t } = useI18n();
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
const nextPlan = computed(() => plans.value.find((plan) => new Date(plan.stTime).getTime() > Date.now()) ?? null);
const metrics = computed<DeviceMetric[]>(() => [
  { label: t("screenDevice.registered"), value: String(screens.value.length), note: t("screenDevice.activeRecords"), tone: "success" },
  { label: t("screenDevice.lastConnection"), value: lastSeenAt.value ? timeLabel(lastSeenAt.value) : t("pair.notReported"), note: lastSeenAt.value ? formatDateTime(lastSeenAt.value) : t("screenDevice.awaitingConnection") },
  { label: t("screenDevice.todayPlans"), value: String(plans.value.length), note: currentPlan.value?.title ?? t("screenDevice.noCurrentPlan"), tone: "warning" },
  { label: t("screenDevice.nextContent"), value: nextPlan.value ? timeLabel(nextPlan.value.stTime) : t("common.notSet"), note: nextPlan.value?.title ?? t("screenDevice.noNextPlan"), tone: "neutral" },
]);
function timeLabel(value: string) {
  return new Date(value).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
}
</script>

<template>
  <div class="device-data-page">
    <PageHeader compact :title="t('screenDevice.title')" :subtitle="t('screenDevice.subtitle')" />
    <DeviceMetricStrip :items="metrics" :label="t('screenDevice.dataSummary')" />
    <section class="device-data-grid">
      <BaseCard :title="t('screenDevice.displaySchedule')">
        <div v-if="currentPlan || nextPlan" class="screen-content-preview">
          <span>{{ currentPlan ? t("screenDevice.currentPlan") : t("screenDevice.nextPlan") }}</span>
          <strong>{{ (currentPlan ?? nextPlan)?.title }}</strong>
          <p>{{ timeLabel((currentPlan ?? nextPlan)?.stTime ?? '') }} · {{ t("screenDevice.duration", { value: (currentPlan ?? nextPlan)?.durationMin ?? 0 }) }}</p>
        </div>
        <EmptyState v-else :text="t('screenDevice.noPlans')" />
        <div v-if="plans.length" class="screen-plan-list"><article v-for="plan in plans.slice(0, 6)" :key="plan.evtId"><time>{{ timeLabel(plan.stTime) }}</time><div><strong>{{ plan.title }}</strong><small>{{ t("screenDevice.duration", { value: plan.durationMin }) }}</small></div></article></div>
      </BaseCard>
      <BaseCard :title="t('screenDevice.parameters')">
        <p class="device-data-note">{{ t("screenDevice.parameterNote") }}</p>
        <div class="device-parameter-grid">
          <div><span>{{ t("screenDevice.path") }}</span><strong>/screen</strong></div>
          <div><span>{{ t("screenDevice.transport") }}</span><strong>WebSocket</strong></div>
          <div><span>{{ t("screenDevice.channel") }}</span><strong>screen</strong></div>
          <div><span>{{ t("screenDevice.credential") }}</span><strong>{{ t("screenDevice.deviceToken") }}</strong></div>
        </div>
      </BaseCard>
    </section>
    <DeviceManagementPanel icon="SC" :title="t('screenDevice.managementTitle')" :summary="t('screenDevice.managementSummary', { count: screens.length })"><DevicePairPanel embedded :allowed-kinds="['screen']" :title="t('screenDevice.pairTitle')" /></DeviceManagementPanel>
  </div>
</template>
