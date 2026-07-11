<script setup lang="ts">
import { computed } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import EventCard from "@/components/events/EventCard.vue";
import { deviceApi } from "@/api/device";
import { eventApi } from "@/api/event";
import { ideaApi } from "@/api/idea";
import { todayKey } from "@/utils/date";
import { sortEvents } from "@/utils/event";

const { t } = useI18n();
const eventsQuery = useQuery({ queryKey: ["events", "overview"], queryFn: () => eventApi.list({ date: todayKey(), includeReminders: true }) });
const ddlQuery = useQuery({ queryKey: ["events", "deadlines"], queryFn: () => eventApi.list({ evtType: ["ddl"] }) });
const ideasQuery = useQuery({ queryKey: ["ideas"], queryFn: ideaApi.list });
const deviceQuery = useQuery({ queryKey: ["device", "latest"], queryFn: () => deviceApi.latest() });
const events = computed(() => sortEvents(eventsQuery.data.value ?? []));
const todos = computed(() => events.value.filter((event) => event.stat === "todo").length);
const future72 = computed(() => {
  const now = Date.now(), end = now + 72 * 3_600_000;
  return (ddlQuery.data.value ?? []).filter((event) => event.evtType === "ddl" && event.stat === "todo" && new Date(event.endTime).getTime() >= now && new Date(event.endTime).getTime() <= end);
});
const openIdeas = computed(() => (ideasQuery.data.value ?? []).filter((idea) => !idea.handled));
</script>
<template>
  <section class="page-heading"><div><h1>{{ t("overview.title") }}</h1><p>{{ t("overview.subtitle") }}</p></div></section>
  <section class="summary-grid">
    <article><span>{{ t("overview.todo") }}</span><strong>{{ todos }}</strong></article>
    <article><span>{{ t("overview.today") }}</span><strong>{{ events.length }}</strong></article>
    <article><span>{{ t("overview.deadline") }}</span><strong>{{ future72.length }}</strong></article>
    <article><span>{{ t("overview.ideas") }}</span><strong>{{ openIdeas.length }}</strong></article>
  </section>
  <section class="dashboard-grid">
    <BaseCard :title="t('overview.today')"><div class="event-list"><EventCard v-for="event in events" :key="event.evtId" :event="event" @select="$router.push({ name: 'update', query: { date: todayKey(), event: event.evtId } })" /><EmptyState v-if="!events.length" /></div></BaseCard>
    <div class="stack">
      <BaseCard :title="t('overview.upcoming')"><div class="event-list"><EventCard v-for="event in future72" :key="event.evtId" :event="event" @select="$router.push({ name: 'update', query: { event: event.evtId } })" /><EmptyState v-if="!future72.length" /></div></BaseCard>
      <BaseCard :title="t('overview.device')"><div class="device-inline"><span class="state-dot" :class="`state-dot--${deviceQuery.data.value?.state ?? 'offline'}`" /><div><strong>{{ deviceQuery.data.value?.state ?? 'offline' }}</strong><small>{{ deviceQuery.data.value?.seenAt ?? '—' }}</small></div></div></BaseCard>
    </div>
  </section>
</template>
