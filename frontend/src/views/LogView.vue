<script setup lang="ts">
import { computed, ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import PageHeader from "@/components/base/PageHeader.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import { logApi } from "@/api/log";
import type { LogRecord, LogsResponse } from "@/types/log";
import { formatDateTime } from "@/utils/date";

const { t } = useI18n();
const tab = ref<keyof LogsResponse>("act");
const keyword = ref("");
const status = ref("");
const query = useQuery({ queryKey: ["logs"], queryFn: () => logApi.list(300), refetchInterval: 30_000 });

function recordStatus(row: LogRecord): string {
  return String(row.result ?? row.stat ?? row.status ?? "");
}
function recordTime(row: LogRecord): string {
  return String(row.createdAt ?? row.scheduledAt ?? row.sentAt ?? row.receivedAt ?? "");
}
function recordTitle(row: LogRecord): string {
  return String(row.action ?? row.title ?? row.msgType ?? row.targetKind ?? row.channel ?? t("logs.title"));
}
const availableStatuses = computed(() => [...new Set((query.data.value?.[tab.value] ?? []).map(recordStatus).filter(Boolean))]);
const rows = computed(() => (query.data.value?.[tab.value] ?? [])
  .filter((row) => !keyword.value.trim() || JSON.stringify(row).toLowerCase().includes(keyword.value.trim().toLowerCase()))
  .filter((row) => !status.value || recordStatus(row) === status.value));
</script>

<template>
  <PageHeader :title="t('logs.title')" :subtitle="t('logs.subtitle')"><template #actions><button class="button" @click="query.refetch()">{{ t("common.refresh") }}</button></template></PageHeader>
  <BaseCard>
    <div class="tabs"><button v-for="name in ['act','notify','msg']" :key="name" class="tab" :class="{ 'tab--active': tab === name }" @click="tab = name as keyof LogsResponse; status = ''">{{ t(`logs.${name}`) }}</button></div>
    <div class="filter-row"><input v-model="keyword" class="wide-input" :placeholder="t('common.search')" /><select v-model="status"><option value="">{{ t("logs.allStatus") }}</option><option v-for="item in availableStatuses" :key="item" :value="item">{{ item }}</option></select></div>
    <div class="log-cards"><details v-for="(row, index) in rows" :key="index"><summary><strong>{{ recordTitle(row) }}</strong><span>{{ recordStatus(row) || t('common.notSet') }} · {{ formatDateTime(recordTime(row)) }}</span></summary><pre>{{ JSON.stringify(row, null, 2) }}</pre></details><EmptyState v-if="!rows.length" /></div>
  </BaseCard>
</template>
