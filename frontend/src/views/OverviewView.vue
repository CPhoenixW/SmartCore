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
import { eventDateKey, todayKey } from "@/utils/date";
import { sortEvents } from "@/utils/event";

const { t } = useI18n();
const eventsQuery = useQuery({ queryKey: ["events", "overview-all"], queryFn: () => eventApi.list({ includeReminders: true, includeCourseTemplates: false }) });
const ideasQuery = useQuery({ queryKey: ["ideas"], queryFn: ideaApi.list });
const deviceQuery = useQuery({ queryKey: ["device", "latest"], queryFn: () => deviceApi.latest(), refetchInterval: 10_000 });

const actionable = computed(() => sortEvents((eventsQuery.data.value ?? []).filter((event) => event.evtType !== "course")));
const todayEvents = computed(() => actionable.value.filter((event) => eventDateKey(event) === todayKey()));
const todos = computed(() => actionable.value.filter((event) => event.stat === "todo"));
const future72 = computed(() => {
  const now = Date.now();
  const end = now + 72 * 3_600_000;
  return actionable.value.filter((event) => event.evtType === "ddl" && event.stat === "todo" && new Date(event.endTime).getTime() >= now && new Date(event.endTime).getTime() <= end);
});
const openIdeas = computed(() => (ideasQuery.data.value ?? []).filter((idea) => !idea.handled));
const recentIdeas = computed(() => [...openIdeas.value].slice(-5).reverse());
const deviceMeta = computed(() => {
  const raw = deviceQuery.data.value?.meta;
  if (raw && typeof raw === "object") return raw;
  if (typeof raw === "string") {
    try { return JSON.parse(raw) as Record<string, unknown>; } catch { return {}; }
  }
  return {};
});
const devicePersons = computed(() => {
  const persons = deviceMeta.value.persons;
  if (!Array.isArray(persons)) return "—";
  return persons.map((person) => typeof person === "object" && person ? String((person as Record<string, unknown>).name ?? (person as Record<string, unknown>).personId ?? "") : "").filter(Boolean).join("、") || "—";
});
</script>

<template>
  <section class="page-heading"><div><h1>{{ t("overview.title") }}</h1><p>{{ t("overview.subtitle") }}</p></div></section>
  <section class="summary-grid">
    <article><span>{{ t("overview.todo") }}</span><strong>{{ todos.length }}</strong></article>
    <article><span>{{ t("overview.today") }}</span><strong>{{ todayEvents.length }}</strong></article>
    <article><span>{{ t("overview.deadline") }}</span><strong>{{ future72.length }}</strong></article>
    <article><span>{{ t("overview.ideas") }}</span><strong>{{ openIdeas.length }}</strong></article>
  </section>
  <section class="dashboard-grid">
    <BaseCard :title="t('overview.today')">
      <div class="event-list">
        <EventCard v-for="event in todayEvents" :key="event.evtId" :event="event" @select="$router.push({ name: 'update', query: { date: eventDateKey(event), evtId: event.evtId } })" />
        <EmptyState v-if="!todayEvents.length" />
      </div>
    </BaseCard>
    <div class="stack">
      <BaseCard :title="t('overview.upcoming')"><div class="event-list"><EventCard v-for="event in future72" :key="event.evtId" :event="event" @select="$router.push({ name: 'update', query: { date: eventDateKey(event), evtId: event.evtId } })" /><EmptyState v-if="!future72.length" /></div></BaseCard>
      <BaseCard :title="t('overview.device')">
        <div class="device-inline"><span class="state-dot" :class="`state-dot--${deviceQuery.data.value?.state ?? 'offline'}`" /><div><strong>{{ deviceQuery.data.value?.state ?? 'offline' }}</strong><small>{{ deviceQuery.data.value?.seenAt ?? '—' }}</small></div></div>
        <div class="kv-grid compact-grid"><div><span>人物</span><strong>{{ devicePersons }}</strong></div><div><span>置信度</span><strong>{{ deviceQuery.data.value?.confidence == null ? '—' : `${Math.round(Number(deviceQuery.data.value.confidence) * 100)}%` }}</strong></div><div><span>是否有人</span><strong>{{ deviceMeta.present ? '有人' : '无人' }}</strong></div></div>
      </BaseCard>
    </div>
  </section>
  <section class="dashboard-grid secondary-grid">
    <BaseCard title="最近灵感"><div class="idea-list compact-list"><article v-for="idea in recentIdeas" :key="idea.ideaId"><button @click="$router.push({ name: 'ideas' })"><strong>{{ idea.content }}</strong><small>{{ idea.createdAt }}</small></button></article><EmptyState v-if="!recentIdeas.length" /></div></BaseCard>
    <BaseCard title="快捷入口"><div class="quick-grid"><RouterLink :to="{ name: 'add' }">添加事件</RouterLink><RouterLink :to="{ name: 'ideas' }">记录灵感</RouterLink><RouterLink :to="{ name: 'course' }">课表管理</RouterLink><RouterLink :to="{ name: 'device' }">设备状态</RouterLink></div></BaseCard>
  </section>
</template>
