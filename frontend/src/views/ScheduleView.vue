<script setup lang="ts">
import { computed, ref } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { CalendarDays, Plus } from "@lucide/vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import PageHeader from "@/components/base/PageHeader.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import EventCard from "@/components/events/EventCard.vue";
import { eventApi } from "@/api/event";
import { runtimeApi } from "@/api/runtime";
import { useToast } from "@/composables/useToast";
import type { SmartCoreEvent } from "@/types/event";
import { addDays, eventDateKey, getEventPrimaryTime } from "@/utils/date";
import { sortEvents } from "@/utils/event";

const { t } = useI18n();
const router = useRouter();
const toast = useToast();
const queryClient = useQueryClient();
const clockQuery = useQuery({ queryKey: ["runtime-clock"], queryFn: () => runtimeApi.clock(), refetchInterval: 60_000 });
const scheduleViews = ["today", "week", "72h"] as const;
type ScheduleView = typeof scheduleViews[number];
const view = ref<ScheduleView>("today");
const eventsQuery = useQuery({
  queryKey: ["schedule", "all"],
  queryFn: () => eventApi.list({ includeReminders: true, includeCourseTemplates: false }),
});
const serverTimezone = computed(() => clockQuery.data.value?.timezone || "Asia/Shanghai");
const serverNow = computed(() => {
  const raw = clockQuery.data.value?.serverNow;
  const parsed = raw ? new Date(raw) : new Date();
  return Number.isFinite(parsed.getTime()) ? parsed : new Date();
});
const serverDate = computed(() => {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: serverTimezone.value, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(serverNow.value);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
});
function eventServerDate(event: SmartCoreEvent): string {
  const primary = getEventPrimaryTime(event);
  if (!primary) return "";
  const parsed = new Date(primary.includes("T") ? primary : `${primary}T12:00:00`);
  if (!Number.isFinite(parsed.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: serverTimezone.value, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(parsed);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}
const rangeEvents = computed(() => {
  const start = serverNow.value.getTime();
  const today = serverDate.value;
  const end = view.value === "today"
    ? new Date(`${today}T23:59:59`).getTime()
    : view.value === "week"
      ? new Date(`${addDays(today, 7)}T00:00:00`).getTime()
      : start + 72 * 60 * 60 * 1000;
  return sortEvents((eventsQuery.data.value ?? []).filter((event) => {
    if (event.stat === "cancelled") return false;
    const primary = getEventPrimaryTime(event);
    const timestamp = primary ? new Date(primary).getTime() : Number.NaN;
    if (view.value === "today") return eventServerDate(event) === today;
    if (Number.isNaN(timestamp)) return false;
    return timestamp >= (view.value === "72h" ? start : new Date(`${today}T00:00:00`).getTime()) && timestamp < end;
  }));
});
const statusMutation = useMutation({
  mutationFn: ({ event, stat }: { event: SmartCoreEvent; stat: "todo" | "done" }) => eventApi.update(event.evtId, { stat }),
  onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["schedule"] }); await queryClient.invalidateQueries({ queryKey: ["events"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
function openEvent(event: SmartCoreEvent): void {
  void router.push({ name: "update", query: { date: eventDateKey(event), evtId: event.evtId } });
}
function setView(value: ScheduleView): void { view.value = value; }
</script>

<template>
  <div class="schedule-page">
    <PageHeader :title="t('schedule.title')" :subtitle="t('schedule.subtitle')">
      <template #actions><RouterLink class="button button--primary" :to="{ name: 'add' }"><Plus :size="16" aria-hidden="true" />{{ t("schedule.add") }}</RouterLink></template>
    </PageHeader>
    <section class="schedule-tabs" role="tablist" :aria-label="t('schedule.rangeLabel')">
      <button v-for="item in scheduleViews" :key="item" class="schedule-tab" :class="{ 'schedule-tab--active': view === item }" type="button" role="tab" :aria-selected="view === item" @click="setView(item)">{{ t(`schedule.${item}`) }}</button>
    </section>
    <section class="schedule-card card">
      <div class="schedule-card__header"><div><CalendarDays :size="18" aria-hidden="true" /><strong>{{ t(`schedule.${view}Title`) }}</strong></div><span>{{ rangeEvents.length }}{{ t("schedule.items") }}</span></div>
      <div v-if="eventsQuery.isPending.value" class="empty-state">{{ t("common.loading") }}</div>
      <div v-else-if="eventsQuery.isError.value" class="schedule-error">{{ t("schedule.error") }}<button class="button" type="button" @click="eventsQuery.refetch()">{{ t("common.retry") }}</button></div>
      <div v-else class="schedule-list">
        <article v-for="event in rangeEvents" :key="event.evtId" class="schedule-item">
          <button class="schedule-item__toggle" type="button" :aria-label="event.stat === 'done' ? t('event.action.markTodo') : t('event.action.markDone')" :disabled="statusMutation.isPending.value" @click="statusMutation.mutate({ event, stat: event.stat === 'done' ? 'todo' : 'done' })"><span :class="{ 'schedule-item__check--done': event.stat === 'done' }">{{ event.stat === 'done' ? '✓' : '' }}</span></button>
          <EventCard :event="event" @select="openEvent" />
        </article>
        <EmptyState v-if="!rangeEvents.length" :text="t('schedule.empty')" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.schedule-page{display:grid;gap:16px}.schedule-tabs{display:flex;gap:7px;overflow:auto}.schedule-tab{min-height:44px;padding:9px 15px;border:1px solid var(--border-color);border-radius:999px;background:#fff;color:var(--color-text-muted);font:inherit;white-space:nowrap}.schedule-tab--active{border-color:#93c5fd;background:#eff6ff;color:#1d4ed8}.schedule-card{overflow:hidden}.schedule-card__header{display:flex;align-items:center;justify-content:space-between;padding:17px 19px;border-bottom:1px solid var(--border-color)}.schedule-card__header>div{display:flex;align-items:center;gap:8px}.schedule-card__header>span{color:var(--color-text-muted);font-size:13px}.schedule-list{display:grid;gap:10px;padding:16px}.schedule-item{display:grid;grid-template-columns:32px minmax(0,1fr);align-items:start;gap:8px}.schedule-item__toggle{display:grid;place-items:center;width:32px;height:32px;border:1px solid var(--border-color);border-radius:50%;background:#fff;color:#fff}.schedule-item__toggle span{display:grid;place-items:center;width:22px;height:22px;border-radius:50%;color:transparent}.schedule-item__check--done{background:#16a34a;color:#fff!important}.schedule-error{display:flex;align-items:center;justify-content:center;gap:10px;padding:40px;color:var(--color-danger)}
</style>
