<script setup lang="ts">
import { computed, ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import { logApi } from "@/api/log";
import type { LogsResponse } from "@/types/log";
const { t } = useI18n(); const tab = ref<keyof LogsResponse>("act"); const keyword = ref("");
const query = useQuery({ queryKey: ["logs"], queryFn: () => logApi.list() });
const rows = computed(() => (query.data.value?.[tab.value] ?? []).filter((row) => JSON.stringify(row).toLowerCase().includes(keyword.value.toLowerCase())));
</script>
<template><section class="page-heading"><div><h1>{{ t("logs.title") }}</h1><p>{{ t("logs.subtitle") }}</p></div></section><BaseCard><div class="tabs"><button v-for="name in ['act','notify','msg']" :key="name" class="tab" :class="{ 'tab--active': tab === name }" @click="tab = name as keyof LogsResponse">{{ t(`logs.${name}`) }}</button></div><input v-model="keyword" class="wide-input" :placeholder="t('common.search')" /><div class="log-table"><article v-for="(row, index) in rows" :key="index"><code>{{ JSON.stringify(row, null, 2) }}</code></article><EmptyState v-if="!rows.length" /></div></BaseCard></template>
