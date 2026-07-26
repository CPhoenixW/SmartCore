<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import DevicePairPanel from "@/components/device/DevicePairPanel.vue";
import DeviceManagementPanel from "@/components/device/DeviceManagementPanel.vue";
import DeviceMetricStrip, { type DeviceMetric } from "@/components/device/DeviceMetricStrip.vue";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import BarChart, { type BarChartSeries } from "@/components/base/BarChart.vue";
import { deviceApi } from "@/api/device";
import { deviceRegistryApi } from "@/api/deviceRegistry";
import { useToast } from "@/composables/useToast";
import type { DeviceUsagePoint, PhotoRequest } from "@/types/device";
import { formatDateTime } from "@/utils/date";
import { devicePersonNames, deviceStateView } from "@/utils/device";

const { t, locale } = useI18n();
const toast = useToast();
const queryClient = useQueryClient();
const search = ref("");
const activeRequestId = ref<string | null>(null);
const displayedPhoto = ref<PhotoRequest | null>(null);
const registeredDevices = useQuery({ queryKey: ["lifeDevices"], queryFn: deviceRegistryApi.list, refetchInterval: 15_000 });
const activeDeviceId = computed(() => {
  const devices = registeredDevices.data.value ?? [];
  return devices.find((device) => device.deviceKind === "pi")?.deviceId ?? "";
});
const latest = useQuery({ queryKey: ["device", "latest", activeDeviceId], queryFn: () => deviceApi.latest(activeDeviceId.value), enabled: computed(() => Boolean(activeDeviceId.value)), refetchInterval: 10_000 });
const recent = useQuery({ queryKey: ["device", "recent", activeDeviceId], queryFn: () => deviceApi.recent(activeDeviceId.value, 240), enabled: computed(() => Boolean(activeDeviceId.value)), refetchInterval: 60_000 });
const usage = useQuery({ queryKey: ["device", "usage", activeDeviceId, 24], queryFn: () => deviceApi.recentUsage(activeDeviceId.value, 24), enabled: computed(() => Boolean(activeDeviceId.value)), refetchInterval: 60_000 });
const photos = useQuery({ queryKey: ["device", "photos", activeDeviceId], queryFn: () => deviceApi.photoRequests(activeDeviceId.value), enabled: computed(() => Boolean(activeDeviceId.value)), refetchInterval: 2_000 });
const currentView = computed(() => deviceStateView(latest.data.value));
const names = computed(() => devicePersonNames(currentView.value));
const logs = computed(() => (recent.data.value ?? []).filter((row) => {
  const view = deviceStateView(row, Number.MAX_SAFE_INTEGER);
  const haystack = `${view.state} ${view.seenAt} ${devicePersonNames(view).join(" ")} ${JSON.stringify(view.meta)}`.toLowerCase();
  return !search.value.trim() || haystack.includes(search.value.trim().toLowerCase());
}));
const activePhoto = computed(() => (photos.data.value ?? []).find((item) => item.requestId === activeRequestId.value));
const photoUrl = computed(() => displayedPhoto.value?.imageUrl ? `${displayedPhoto.value.imageUrl}?t=${encodeURIComponent(displayedPhoto.value.completedAt ?? "")}` : "");
const usagePoints = computed(() => usage.data.value?.points ?? []);
const usageLabels = computed(() => usagePoints.value.map((point) => usageTimeLabel(point.startAt)));
const usageDetails = computed(() => usagePoints.value.map(usageTooltip));
const usageSeries = computed<BarChartSeries[]>(() => [{
  key: "usage",
  name: t("device.usageSeries"),
  color: "#2563eb",
  values: usagePoints.value.map((point) => point.minutes),
  displayValues: usagePoints.value.map((point) => t("device.minutesValue", { value: Math.round(point.minutes) })),
}]);
const activeDevice = computed(() => (registeredDevices.data.value ?? []).find((device) => device.deviceId === activeDeviceId.value));
const metrics = computed<DeviceMetric[]>(() => [
  {
    label: t("device.latest"),
    value: stateLabel(currentView.value.state),
    note: currentView.value.seenAt ? formatDateTime(currentView.value.seenAt) : t("common.notSet"),
    tone: currentView.value.state === "working" ? "success" : currentView.value.state === "away" ? "warning" : "neutral",
  },
  {
    label: t("device.present"),
    value: currentView.value.present ? t("device.presentYes") : t("device.presentNo"),
    note: names.value.join(t("common.listSeparator")) || t("device.unidentified"),
  },
  {
    label: t("device.stateConfidence"),
    value: currentView.value.confidence == null ? t("common.notSet") : `${Math.round(currentView.value.confidence * 100)}%`,
    note: usage.data.value?.averageConfidence == null ? t("device.noAverageConfidence") : t("device.averageConfidenceNote", { value: Math.round(usage.data.value.averageConfidence * 100) }),
    tone: "warning",
  },
  {
    label: t("device.lastReport"),
    value: currentView.value.seenAt ? usageTimeLabel(currentView.value.seenAt) : t("common.notSet"),
    note: activeDevice.value?.deviceName ?? t("device.piTitle"),
    tone: "neutral",
  },
]);
const requestPhoto = useMutation({
  mutationFn: () => deviceApi.requestPhoto(activeDeviceId.value),
  onSuccess: async (request) => {
    displayedPhoto.value = null;
    activeRequestId.value = request.requestId;
    toast.success(t("device.photoRequested"));
    await queryClient.invalidateQueries({ queryKey: ["device", "photos"] });
  },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
watch(activePhoto, (item, previous) => {
  if (!item || item.stat === previous?.stat) return;
  if (item.stat === "uploaded") {
    displayedPhoto.value = item;
    toast.success(t("device.photoReturned"));
    activeRequestId.value = null;
  }
  if (["failed", "expired", "cancelled"].includes(item.stat)) {
    toast.error(item.errorMessage || t("device.photoFailed"));
    activeRequestId.value = null;
    displayedPhoto.value = null;
  }
});
onBeforeUnmount(() => {
  displayedPhoto.value = null;
  activeRequestId.value = null;
});
async function refreshAll() {
  await Promise.all([registeredDevices.refetch(), latest.refetch(), recent.refetch(), usage.refetch(), photos.refetch()]);
}
function photoMeta(item: PhotoRequest | null | undefined) {
  if (!item) return t("device.noPhotoRequest");
  const knownStatuses = new Set(["pending", "uploaded", "failed", "expired", "cancelled"]);
  const statusLabel = knownStatuses.has(item.stat) ? t(`device.photoStatus.${item.stat}`) : item.stat;
  return `${statusLabel} · ${formatDateTime(item.capturedAt ?? item.requestedAt)}`;
}
function usageTimeLabel(value: string) {
  return new Date(value).toLocaleTimeString(locale.value === "en-US" ? "en-US" : "zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: usage.data.value?.timezone ?? "Asia/Shanghai",
  });
}
function usageTooltip(point: DeviceUsagePoint) {
  return t("device.usageTooltip", {
    start: usageTimeLabel(point.startAt),
    end: usageTimeLabel(point.endAt),
    minutes: Math.round(point.minutes),
  });
}
function stateLabel(state: string) {
  return ["working", "away", "offline", "unknown"].includes(state) ? t(`device.state.${state}`) : state;
}
</script>

<template>
  <div class="device-data-page">
    <DeviceMetricStrip :items="metrics" :label="t('device.dataSummary')" />

    <section class="device-data-grid device-data-grid--pi device-data-grid--matched">
      <BaseCard :title="t('device.usage')"><template #actions><button class="button" @click="refreshAll">{{ t("common.refresh") }}</button></template>
        <div class="usage-summary">
          <div><span>{{ t("device.total") }}</span><strong>{{ t("device.minutesValue", { value: Math.round(usage.data.value?.totalMinutes ?? 0) }) }}</strong></div>
          <div><span>{{ t("device.peak") }}</span><strong>{{ usage.data.value?.peakStartAt ? usageTimeLabel(usage.data.value.peakStartAt) : t('common.notSet') }}</strong></div>
          <div><span>{{ t("device.confidence") }}</span><strong>{{ usage.data.value?.averageConfidence == null ? t('common.notSet') : `${Math.round(usage.data.value.averageConfidence * 100)}%` }}</strong></div>
        </div>
        <BarChart v-if="usagePoints.length" :labels="usageLabels" :details="usageDetails" :series="usageSeries" :label="t('device.usage')" />
        <EmptyState v-else :text="t('device.noUsage')" />
        <p class="chart-hint">{{ t("device.scrollHint") }}</p>
      </BaseCard>

      <BaseCard :title="t('device.photo')"><template #actions><button class="button button--primary" :disabled="requestPhoto.isPending.value || Boolean(activeRequestId)" @click="requestPhoto.mutate()">{{ activeRequestId ? t('device.waiting') : t('device.requestPhoto') }}</button></template><div class="camera-frame"><img v-if="photoUrl" :src="photoUrl" :alt="t('device.photoAlt')" /><div v-else class="camera-placeholder"><EmptyState :text="activeRequestId ? t('device.waitingForReturn') : t('device.readyForPhoto')" /></div></div><p class="camera-meta">{{ photoMeta(activePhoto ?? displayedPhoto) }}</p></BaseCard>
    </section>

    <section class="device-data-grid device-data-grid--pi device-data-grid--scroll-pair">
      <BaseCard :title="`${t('device.recent')} · ${logs.length}`"><template #actions><input v-model="search" class="compact-search" :placeholder="t('device.searchPlaceholder')" /></template><div class="log-list device-scroll-list"><details v-for="row in logs" :key="row.stateLogId ?? row.seenAt" class="device-log-detail"><summary><span><i class="state-dot" :class="`state-dot--${deviceStateView(row, Number.MAX_SAFE_INTEGER).state}`" />{{ stateLabel(deviceStateView(row, Number.MAX_SAFE_INTEGER).state) }} · {{ devicePersonNames(deviceStateView(row, Number.MAX_SAFE_INTEGER)).join(t('common.listSeparator')) || t('device.unidentifiedPerson') }}</span><small>{{ formatDateTime(row.seenAt) }} · {{ row.confidence == null ? t('common.notSet') : `${Math.round(Number(row.confidence) * 100)}%` }}</small></summary><pre>{{ JSON.stringify(row, null, 2) }}</pre></details><EmptyState v-if="!logs.length" /></div></BaseCard>
      <BaseCard :title="t('device.collectionHealth')"><div class="device-parameter-grid device-parameter-grid--health"><div><span>{{ t("device.clockSkew") }}</span><strong>{{ currentView.meta.clockSkewSeconds == null ? t('common.notSet') : t("device.seconds", { value: Number(currentView.meta.clockSkewSeconds).toFixed(2) }) }}</strong></div><div><span>{{ t("device.model") }}</span><strong>{{ currentView.meta.model || t('common.notSet') }}</strong></div><div><span>{{ t("device.camera") }}</span><strong>{{ currentView.meta.camera || t('common.notSet') }}</strong></div><div><span>{{ t("device.sampleCount") }}</span><strong>{{ usage.data.value?.sampleCount ?? 0 }}</strong></div><div><span>{{ t("device.averageConfidence") }}</span><strong>{{ usage.data.value?.averageConfidence == null ? t('common.notSet') : `${Math.round(usage.data.value.averageConfidence * 100)}%` }}</strong></div><div><span>{{ t("device.total") }}</span><strong>{{ t("device.minutesValue", { value: Math.round(usage.data.value?.totalMinutes ?? 0) }) }}</strong></div><div><span>{{ t("device.reportedAt") }}</span><strong>{{ currentView.meta.reportedAt ? formatDateTime(String(currentView.meta.reportedAt)) : t('common.notSet') }}</strong></div><div><span>{{ t("device.deviceStatus") }}</span><strong>{{ activeDevice?.stat || t('common.notSet') }}</strong></div></div></BaseCard>
    </section>

    <DeviceManagementPanel icon="Pi" :title="t('device.managementTitle')" :summary="t('device.managementSummary', { count: activeDevice ? 1 : 0 })"><DevicePairPanel embedded :allowed-kinds="['pi']" :title="t('device.piPairTitle')" /></DeviceManagementPanel>
  </div>
</template>
