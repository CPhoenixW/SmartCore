<script setup lang="ts">
import { computed } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import { deviceApi } from "@/api/device";
import { useToast } from "@/composables/useToast";

const { t } = useI18n(); const toast = useToast(); const queryClient = useQueryClient();
const latest = useQuery({ queryKey: ["device", "latest"], queryFn: () => deviceApi.latest() });
const recent = useQuery({ queryKey: ["device", "recent"], queryFn: () => deviceApi.recent() });
const usage = useQuery({ queryKey: ["device", "usage"], queryFn: () => deviceApi.usageToday() });
const photos = useQuery({ queryKey: ["device", "photos"], queryFn: () => deviceApi.photoRequests(), refetchInterval: 5000 });
const requestPhoto = useMutation({ mutationFn: () => deviceApi.requestPhoto(), onSuccess: async () => { toast.success("Photo requested"); await queryClient.invalidateQueries({ queryKey: ["device", "photos"] }); } });
const latestPhoto = computed(() => (photos.data.value ?? []).find((item) => item.stat === "uploaded"));
const photoId = computed(() => latestPhoto.value?.requestId ?? latestPhoto.value?.id ?? "");
const maxUsage = computed(() => Math.max(1, ...(usage.data.value?.hourlyMinutes ?? [1])));
</script>
<template>
  <section class="page-heading"><div><h1>{{ t("device.title") }}</h1><p>{{ t("device.subtitle") }}</p></div></section>
  <section class="device-layout">
    <div class="stack"><BaseCard :title="t('device.latest')"><template #actions><button class="button" @click="latest.refetch()">{{ t("common.refresh") }}</button></template><div class="device-status"><span class="state-dot large" :class="`state-dot--${latest.data.value?.state ?? 'offline'}`" /><div><strong>{{ latest.data.value?.state ?? "offline" }}</strong><small>{{ latest.data.value?.seenAt ?? "—" }}</small></div></div><div class="kv-grid"><div><span>present</span><strong>{{ latest.data.value?.present ?? "—" }}</strong></div><div><span>confidence</span><strong>{{ latest.data.value?.confidence ?? "—" }}</strong></div><div><span>device</span><strong>{{ latest.data.value?.deviceId ?? "pi" }}</strong></div></div></BaseCard><BaseCard :title="t('device.recent')"><div class="log-list"><article v-for="row in recent.data.value ?? []" :key="row.seenAt"><strong>{{ row.state }}</strong><span>{{ row.seenAt }}</span><small>{{ row.confidence }}</small></article><EmptyState v-if="!(recent.data.value ?? []).length" /></div></BaseCard></div>
    <div class="stack"><BaseCard :title="t('device.photo')"><template #actions><button class="button button--primary" @click="requestPhoto.mutate()">{{ t("device.requestPhoto") }}</button></template><div class="camera-frame"><img v-if="photoId" :src="deviceApi.photoImageUrl(photoId)" alt="camera" /><EmptyState v-else /></div></BaseCard><BaseCard :title="t('device.usage')"><div class="usage-summary"><div><span>{{ t("device.total") }}</span><strong>{{ usage.data.value?.totalMinutes ?? 0 }} min</strong></div><div><span>{{ t("device.peak") }}</span><strong>{{ usage.data.value?.peakHour ?? "—" }}</strong></div><div><span>{{ t("device.confidence") }}</span><strong>{{ usage.data.value?.averageConfidence?.toFixed(2) ?? "—" }}</strong></div></div><div class="bar-chart"><div v-for="(value, hour) in usage.data.value?.hourlyMinutes ?? []" :key="hour" class="bar-column"><span :style="{ height: `${(value / maxUsage) * 100}%` }" /><small>{{ hour }}</small></div></div></BaseCard></div>
  </section>
</template>
