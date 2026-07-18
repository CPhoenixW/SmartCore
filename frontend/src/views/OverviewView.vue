<script setup lang="ts">
import { computed, ref } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import EventCard from "@/components/events/EventCard.vue";
import EventStatusToggle from "@/components/events/EventStatusToggle.vue";
import { deviceApi } from "@/api/device";
import { deviceRegistryApi } from "@/api/deviceRegistry";
import { eventApi } from "@/api/event";
import { ideaApi } from "@/api/idea";
import { useToast } from "@/composables/useToast";
import type { SmartCoreEvent } from "@/types/event";
import { addDays, eventDateKey, todayKey } from "@/utils/date";
import { sortEvents } from "@/utils/event";

const { t } = useI18n();
const queryClient = useQueryClient();
const toast = useToast();
const selectedDate = ref(todayKey());
const eventsQuery = useQuery({ queryKey: ["events", "overview-all"], queryFn: () => eventApi.list({ includeReminders: true, includeCourseTemplates: false }) });
const dayEventsQuery = useQuery({
  queryKey: computed(() => ["events", "overview-day", selectedDate.value]),
  queryFn: () => eventApi.list({ date: selectedDate.value, includeReminders: true, includeCourseTemplates: false }),
});
const ideasQuery = useQuery({ queryKey: ["ideas"], queryFn: ideaApi.list });
const registeredDevices = useQuery({ queryKey: ["lifeDevices"], queryFn: deviceRegistryApi.list, refetchInterval: 15_000 });
const deviceId = computed(() => {
  const devices = registeredDevices.data.value ?? [];
  return devices.find((device) => device.deviceKind === "pi")?.deviceId ?? devices[0]?.deviceId ?? "";
});
const deviceQuery = useQuery({ queryKey: ["device", "latest", deviceId], queryFn: () => deviceApi.latest(deviceId.value), enabled: computed(() => Boolean(deviceId.value)), refetchInterval: 10_000 });

const actionable = computed(() => sortEvents((eventsQuery.data.value ?? []).filter((event) => event.evtType !== "course" && event.stat !== "cancelled")));
const todayEvents = computed(() => actionable.value.filter((event) => eventDateKey(event) === todayKey()));
const selectedDateEvents = computed(() => sortEvents((dayEventsQuery.data.value ?? []).filter((event) => event.evtType !== "course" && event.stat !== "cancelled")));
const selectedDateTitle = computed(() => selectedDate.value === todayKey() ? t("overview.today") : selectedDate.value);
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
  if (!Array.isArray(persons)) return t("common.notSet");
  return persons.map((person) => typeof person === "object" && person ? String((person as Record<string, unknown>).name ?? (person as Record<string, unknown>).personId ?? "") : "").filter(Boolean).join(t("common.listSeparator")) || t("common.notSet");
});
const deviceState = computed(() => String(deviceQuery.data.value?.state ?? "offline"));
const deviceTitle = computed(() => {
  const device = (registeredDevices.data.value ?? []).find((item) => item.deviceId === deviceId.value);
  return device?.deviceName || t("overview.device");
});
const statusMutation = useMutation({
  mutationFn: ({ event, stat }: { event: SmartCoreEvent; stat: "todo" | "done" }) => eventApi.update(event.evtId, { stat }),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: ["events"] });
  },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
function moveSelectedDate(days: number) {
  selectedDate.value = addDays(selectedDate.value, days);
}
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
    <div class="stack">
    <BaseCard class="overview-today-card" :title="selectedDateTitle">
      <div class="overview-date-toolbar">
        <button class="button" type="button" @click="moveSelectedDate(-1)">{{ t("common.previous") }}</button>
        <input v-model="selectedDate" type="date" :aria-label="t('overview.selectDate')" />
        <button class="button" type="button" @click="selectedDate = todayKey()">{{ t("common.today") }}</button>
        <button class="button" type="button" @click="moveSelectedDate(1)">{{ t("common.next") }}</button>
      </div>
      <div class="event-list">
        <div v-for="event in selectedDateEvents" :key="event.evtId" class="overview-event-row">
          <EventStatusToggle
            :status="event.stat"
            :busy="statusMutation.isPending.value"
            :mark-done-label="t('event.action.markDone')"
            :mark-todo-label="t('event.action.markTodo')"
            @change="statusMutation.mutate({ event, stat: $event })"
          />
          <EventCard :event="event" @select="$router.push({ name: 'update', query: { date: eventDateKey(event), evtId: event.evtId } })" />
        </div>
        <div v-if="dayEventsQuery.isPending.value" class="empty-state">{{ t("common.loading") }}</div>
        <EmptyState v-else-if="!selectedDateEvents.length" class="overview-empty" :text="t('overview.emptySelectedDate')" />
      </div>
    </BaseCard>
    <BaseCard :title="t('overview.recentIdeas')"><div class="idea-list compact-list"><article v-for="idea in recentIdeas" :key="idea.ideaId"><button @click="$router.push({ name: 'ideas' })"><strong>{{ idea.content }}</strong><small>{{ idea.createdAt }}</small></button></article><EmptyState v-if="!recentIdeas.length" /></div></BaseCard>
    </div>
    <div class="stack">
      <BaseCard :title="t('overview.upcoming')"><div class="event-list"><EventCard v-for="event in future72" :key="event.evtId" :event="event" @select="$router.push({ name: 'update', query: { date: eventDateKey(event), evtId: event.evtId } })" /><EmptyState v-if="!future72.length" class="overview-empty" :text="t('overview.emptyDeadline')" /></div></BaseCard>
      <BaseCard :title="deviceTitle">
        <div class="device-inline"><span class="state-dot" :class="`state-dot--${deviceState}`" /><div><strong>{{ t(`device.state.${deviceState}`) }}</strong><small>{{ deviceQuery.data.value?.seenAt ?? t('common.notSet') }}</small></div></div>
        <div class="kv-grid compact-grid"><div><span>{{ t("overview.persons") }}</span><strong>{{ devicePersons }}</strong></div><div><span>{{ t("overview.stateConfidence") }}</span><strong>{{ deviceQuery.data.value?.confidence == null ? t('common.notSet') : `${Math.round(Number(deviceQuery.data.value.confidence) * 100)}%` }}</strong></div><div><span>{{ t("overview.present") }}</span><strong>{{ deviceMeta.present ? t("overview.presentYes") : t("overview.presentNo") }}</strong></div></div>
      </BaseCard>
      <BaseCard :title="t('overview.quickActions')"><div class="quick-grid"><RouterLink :to="{ name: 'add' }">{{ t("overview.addEvent") }}</RouterLink><RouterLink :to="{ name: 'ideas' }">{{ t("overview.captureIdea") }}</RouterLink><RouterLink :to="{ name: 'course' }">{{ t("overview.manageCourses") }}</RouterLink><RouterLink :to="{ name: 'device' }">{{ t("overview.deviceStatus") }}</RouterLink></div></BaseCard>
    </div>
  </section>
</template>

<style scoped>
.overview-date-toolbar {
  display: grid;
  grid-template-columns: auto minmax(150px, 1fr) auto auto;
  gap: 10px;
  margin-bottom: 16px;
}
.overview-date-toolbar input {
  min-width: 0;
  padding: 9px 11px;
  border: 1px solid var(--border-color);
  border-radius: 9px;
  background: #fff;
  color: var(--color-text);
}
.overview-event-row {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  align-items: start;
  gap: 8px;
}
.overview-event-row :deep(.event-card) {
  min-width: 0;
}
@media (max-width: 760px) {
  .overview-date-toolbar {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
