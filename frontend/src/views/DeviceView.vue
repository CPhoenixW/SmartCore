<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import DevicePairPanel from "@/components/device/DevicePairPanel.vue";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import { deviceApi } from "@/api/device";
import { deviceRegistryApi } from "@/api/deviceRegistry";
import { useToast } from "@/composables/useToast";
import type { PhotoRequest } from "@/types/device";
import { formatDateTime } from "@/utils/date";
import { devicePersonNames, deviceStateView } from "@/utils/device";

const { t } = useI18n();
const toast = useToast();
const queryClient = useQueryClient();
const search = ref("");
const activeRequestId = ref<string | null>(null);
const displayedPhoto = ref<PhotoRequest | null>(null);
const registeredDevices = useQuery({ queryKey: ["lifeDevices"], queryFn: deviceRegistryApi.list, refetchInterval: 15_000 });
const activeDeviceId = computed(() => {
  const devices = registeredDevices.data.value ?? [];
  return devices.find((device) => device.deviceKind === "pi")?.deviceId ?? devices[0]?.deviceId ?? "";
});
const latest = useQuery({ queryKey: ["device", "latest", activeDeviceId], queryFn: () => deviceApi.latest(activeDeviceId.value), enabled: computed(() => Boolean(activeDeviceId.value)), refetchInterval: 10_000 });
const recent = useQuery({ queryKey: ["device", "recent", activeDeviceId], queryFn: () => deviceApi.recent(activeDeviceId.value, 240), enabled: computed(() => Boolean(activeDeviceId.value)), refetchInterval: 60_000 });
const usage = useQuery({ queryKey: ["device", "usage", activeDeviceId], queryFn: () => deviceApi.usageToday(activeDeviceId.value), enabled: computed(() => Boolean(activeDeviceId.value)), refetchInterval: 60_000 });
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
const maxUsage = computed(() => Math.max(1, ...(usage.data.value?.hourlyMinutes ?? [1])));
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
async function refreshAll() { await Promise.all([registeredDevices.refetch(), latest.refetch(), recent.refetch(), usage.refetch(), photos.refetch()]); }
function photoMeta(item: PhotoRequest | null | undefined) {
  if (!item) return t("device.noPhotoRequest");
  const knownStatuses = new Set(["pending", "uploaded", "failed", "expired", "cancelled"]);
  const statusLabel = knownStatuses.has(item.stat) ? t(`device.photoStatus.${item.stat}`) : item.stat;
  return `${statusLabel} · ${formatDateTime(item.capturedAt ?? item.requestedAt)}`;
}
function usageTooltip(hour: number, minutes: number) {
  return t("device.usageTooltip", { hour: String(hour).padStart(2, "0"), next: String((hour + 1) % 24).padStart(2, "0"), minutes: Math.round(minutes) });
}
function stateLabel(state: string) {
  return ["working", "away", "offline", "unknown"].includes(state) ? t(`device.state.${state}`) : state;
}
</script>

<template>
  <div class="dual-scroll-page">
    <section class="page-heading"><div><h1>{{ t("device.title") }}</h1><p>{{ t("device.subtitle") }}</p></div><button class="button" @click="refreshAll">{{ t("common.refresh") }}</button></section>
    <section class="split-scroll-layout">
      <div class="split-scroll-column split-scroll-column--main">
        <div class="stack"><DevicePairPanel />
          <BaseCard :title="t('device.latest')"><div class="device-status"><span class="state-dot large" :class="`state-dot--${currentView.state}`" /><div><strong>{{ stateLabel(currentView.state) }}</strong><small>{{ currentView.seenAt ? formatDateTime(currentView.seenAt) : t('common.notSet') }}{{ currentView.stale ? ` · ${t('device.offline')}` : '' }}</small></div></div><div class="kv-grid"><div><span>{{ t("device.present") }}</span><strong>{{ currentView.present ? t("device.presentYes") : t("device.presentNo") }}</strong></div><div><span>{{ t("device.persons") }}</span><strong>{{ names.join(t('common.listSeparator')) || t('device.unidentified') }}</strong></div><div><span>{{ t("device.stateConfidence") }}</span><strong>{{ currentView.confidence == null ? t('common.notSet') : `${Math.round(currentView.confidence * 100)}%` }}</strong></div><div><span>{{ t("device.clockSkew") }}</span><strong>{{ currentView.meta.clockSkewSeconds == null ? t('common.notSet') : t("device.seconds", { value: Number(currentView.meta.clockSkewSeconds).toFixed(2) }) }}</strong></div><div><span>{{ t("device.model") }}</span><strong>{{ currentView.meta.model || t('common.notSet') }}</strong></div><div><span>{{ t("device.camera") }}</span><strong>{{ currentView.meta.camera || t('common.notSet') }}</strong></div></div></BaseCard>
          <BaseCard :title="`${t('device.recent')} · ${logs.length}`"><template #actions><input v-model="search" class="compact-search" :placeholder="t('device.searchPlaceholder')" /></template><div class="log-list"><details v-for="row in logs" :key="row.stateLogId ?? row.seenAt" class="device-log-detail"><summary><span><i class="state-dot" :class="`state-dot--${deviceStateView(row, Number.MAX_SAFE_INTEGER).state}`" />{{ stateLabel(deviceStateView(row, Number.MAX_SAFE_INTEGER).state) }} · {{ devicePersonNames(deviceStateView(row, Number.MAX_SAFE_INTEGER)).join(t('common.listSeparator')) || t('device.unidentifiedPerson') }}</span><small>{{ formatDateTime(row.seenAt) }} · {{ row.confidence == null ? t('common.notSet') : `${Math.round(Number(row.confidence) * 100)}%` }}</small></summary><pre>{{ JSON.stringify(row, null, 2) }}</pre></details><EmptyState v-if="!logs.length" /></div></BaseCard>
        </div>
      </div>
      <aside class="split-scroll-column split-scroll-column--side">
        <div class="stack">
          <BaseCard :title="t('device.photo')"><template #actions><button class="button button--primary" :disabled="requestPhoto.isPending.value || Boolean(activeRequestId)" @click="requestPhoto.mutate()">{{ activeRequestId ? t('device.waiting') : t('device.requestPhoto') }}</button></template><div class="camera-frame"><img v-if="photoUrl" :src="photoUrl" :alt="t('device.photoAlt')" /><div v-else class="camera-placeholder"><EmptyState :text="activeRequestId ? t('device.waitingForReturn') : t('device.readyForPhoto')" /></div></div><p class="camera-meta">{{ photoMeta(activePhoto ?? displayedPhoto) }}</p></BaseCard>
          <BaseCard :title="t('device.usage')"><div class="usage-summary"><div><span>{{ t("device.total") }}</span><strong>{{ t("device.minutesValue", { value: Math.round(usage.data.value?.totalMinutes ?? 0) }) }}</strong></div><div><span>{{ t("device.peak") }}</span><strong>{{ usage.data.value?.peakHour == null ? t('common.notSet') : `${String(usage.data.value.peakHour).padStart(2, '0')}:00–${String((usage.data.value.peakHour + 1) % 24).padStart(2, '0')}:00` }}</strong></div><div><span>{{ t("device.confidence") }}</span><strong>{{ usage.data.value?.averageConfidence == null ? t('common.notSet') : `${Math.round(usage.data.value.averageConfidence * 100)}%` }}</strong></div></div><div class="usage-chart-scroll" tabindex="0"><div class="bar-chart bar-chart--scrollable"><div v-for="(value, hour) in usage.data.value?.hourlyMinutes ?? []" :key="hour" class="bar-column bar-column--fixed" :data-tooltip="usageTooltip(hour, value)"><span :style="{ height: `${Math.max(2, (value / maxUsage) * 100)}%` }" /><small>{{ String(hour).padStart(2, '0') }}:00</small></div></div></div><p class="chart-hint">{{ t("device.scrollHint") }}</p></BaseCard>
        </div>
      </aside>
    </section>
  </div>
</template>
