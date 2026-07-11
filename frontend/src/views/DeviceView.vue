<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import { deviceApi } from "@/api/device";
import { useToast } from "@/composables/useToast";
import type { PhotoRequest } from "@/types/device";
import { formatDateTime } from "@/utils/date";
import { devicePersonNames, deviceStateView } from "@/utils/device";

const { t } = useI18n();
const toast = useToast();
const queryClient = useQueryClient();
const search = ref("");
const activeRequestId = ref<string | null>(null);
const latest = useQuery({ queryKey: ["device", "latest"], queryFn: () => deviceApi.latest(), refetchInterval: 10_000 });
const recent = useQuery({ queryKey: ["device", "recent"], queryFn: () => deviceApi.recent("pi", 240), refetchInterval: 60_000 });
const usage = useQuery({ queryKey: ["device", "usage"], queryFn: () => deviceApi.usageToday(), refetchInterval: 60_000 });
const photos = useQuery({ queryKey: ["device", "photos"], queryFn: () => deviceApi.photoRequests(), refetchInterval: 2_000 });
const currentView = computed(() => deviceStateView(latest.data.value));
const names = computed(() => devicePersonNames(currentView.value));
const logs = computed(() => (recent.data.value ?? []).filter((row) => {
  const view = deviceStateView(row, Number.MAX_SAFE_INTEGER);
  const haystack = `${view.state} ${view.seenAt} ${devicePersonNames(view).join(" ")} ${JSON.stringify(view.meta)}`.toLowerCase();
  return !search.value.trim() || haystack.includes(search.value.trim().toLowerCase());
}));
const latestPhoto = computed(() => (photos.data.value ?? []).find((item) => item.stat === "uploaded" && item.imageAvailable));
const activePhoto = computed(() => (photos.data.value ?? []).find((item) => item.requestId === activeRequestId.value));
const photoUrl = computed(() => latestPhoto.value?.imageUrl ? `${latestPhoto.value.imageUrl}?t=${encodeURIComponent(latestPhoto.value.completedAt ?? "")}` : "");
const maxUsage = computed(() => Math.max(1, ...(usage.data.value?.hourlyMinutes ?? [1])));
const requestPhoto = useMutation({
  mutationFn: () => deviceApi.requestPhoto(),
  onSuccess: async (request) => { activeRequestId.value = request.requestId; toast.success("画面请求已创建，等待树莓派下一次心跳"); await queryClient.invalidateQueries({ queryKey: ["device", "photos"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
watch(activePhoto, (item, previous) => {
  if (!item || item.stat === previous?.stat) return;
  if (item.stat === "uploaded") { toast.success("树莓派画面已返回"); activeRequestId.value = null; }
  if (["failed", "expired", "cancelled"].includes(item.stat)) { toast.error(item.errorMessage || item.stat); activeRequestId.value = null; }
});
async function refreshAll() { await Promise.all([latest.refetch(), recent.refetch(), usage.refetch(), photos.refetch()]); }
function photoMeta(item: PhotoRequest | undefined) { return item ? `${item.stat} · ${formatDateTime(item.capturedAt ?? item.requestedAt)}` : "当前没有进行中的画面请求"; }
</script>

<template>
  <section class="page-heading"><div><h1>{{ t("device.title") }}</h1><p>{{ t("device.subtitle") }}</p></div><button class="button" @click="refreshAll">{{ t("common.refresh") }}</button></section>
  <section class="device-layout">
    <div class="stack">
      <BaseCard :title="t('device.latest')"><div class="device-status"><span class="state-dot large" :class="`state-dot--${currentView.state}`" /><div><strong>{{ currentView.label }}</strong><small>{{ currentView.seenAt ? formatDateTime(currentView.seenAt) : '—' }}{{ currentView.stale ? ' · 已离线' : '' }}</small></div></div><div class="kv-grid"><div><span>是否有人</span><strong>{{ currentView.present ? '有人' : '无人' }}</strong></div><div><span>识别人物</span><strong>{{ names.join('、') || '未识别' }}</strong></div><div><span>状态置信度</span><strong>{{ currentView.confidence == null ? '—' : `${Math.round(currentView.confidence * 100)}%` }}</strong></div><div><span>时钟偏差</span><strong>{{ currentView.meta.clockSkewSeconds == null ? '—' : `${Number(currentView.meta.clockSkewSeconds).toFixed(2)} 秒` }}</strong></div><div><span>识别模型</span><strong>{{ currentView.meta.model || '—' }}</strong></div><div><span>摄像头</span><strong>{{ currentView.meta.camera || '—' }}</strong></div></div></BaseCard>
      <BaseCard :title="`${t('device.recent')} · ${logs.length}`"><template #actions><input v-model="search" class="compact-search" placeholder="搜索人物、状态、模型信息" /></template><div class="log-list"><details v-for="row in logs" :key="row.stateLogId ?? row.seenAt" class="device-log-detail"><summary><span><i class="state-dot" :class="`state-dot--${deviceStateView(row, Number.MAX_SAFE_INTEGER).state}`" />{{ deviceStateView(row, Number.MAX_SAFE_INTEGER).label }} · {{ devicePersonNames(deviceStateView(row, Number.MAX_SAFE_INTEGER)).join('、') || '未识别人物' }}</span><small>{{ formatDateTime(row.seenAt) }} · {{ row.confidence == null ? '—' : `${Math.round(Number(row.confidence) * 100)}%` }}</small></summary><pre>{{ JSON.stringify(row, null, 2) }}</pre></details><EmptyState v-if="!logs.length" /></div></BaseCard>
    </div>
    <div class="stack">
      <BaseCard :title="t('device.photo')"><template #actions><button class="button button--primary" :disabled="requestPhoto.isPending.value || Boolean(activeRequestId)" @click="requestPhoto.mutate()">{{ activeRequestId ? '等待回传…' : t('device.requestPhoto') }}</button></template><div class="camera-frame"><img v-if="photoUrl" :src="photoUrl" alt="camera" /><div v-else class="camera-placeholder"><EmptyState :text="activeRequestId ? '正在等待树莓派回传' : '等待请求当前画面'" /></div></div><p class="camera-meta">{{ photoMeta(activePhoto ?? latestPhoto) }}</p></BaseCard>
      <BaseCard :title="t('device.usage')"><div class="usage-summary"><div><span>{{ t("device.total") }}</span><strong>{{ Math.round(usage.data.value?.totalMinutes ?? 0) }} 分钟</strong></div><div><span>{{ t("device.peak") }}</span><strong>{{ usage.data.value?.peakHour == null ? '—' : `${String(usage.data.value.peakHour).padStart(2, '0')}:00–${String((usage.data.value.peakHour + 1) % 24).padStart(2, '0')}:00` }}</strong></div><div><span>{{ t("device.confidence") }}</span><strong>{{ usage.data.value?.averageConfidence == null ? '—' : `${Math.round(usage.data.value.averageConfidence * 100)}%` }}</strong></div></div><div class="bar-chart"><div v-for="(value, hour) in usage.data.value?.hourlyMinutes ?? []" :key="hour" class="bar-column"><span :style="{ height: `${Math.max(2, (value / maxUsage) * 100)}%` }" :title="`${hour}:00 · ${Math.round(value)} 分钟`" /><small>{{ hour }}</small></div></div></BaseCard>
    </div>
  </section>
</template>
