<script setup lang="ts">
import { computed, ref } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { Plus, Sparkles } from "@lucide/vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import EmptyState from "@/components/base/EmptyState.vue";
import EventCard from "@/components/events/EventCard.vue";
import { eventApi } from "@/api/event";
import { runtimeApi } from "@/api/runtime";
import { useToast } from "@/composables/useToast";
import type { SmartCoreEvent } from "@/types/event";
import { addDays, eventDateKey, getEventPrimaryTime } from "@/utils/date";
import { sortEvents } from "@/utils/event";

/** Phone-only overview: the schedule lives here, so the PWA keeps three tabs. */
const { t, locale } = useI18n();
const router = useRouter();
const toast = useToast();
const queryClient = useQueryClient();
const ranges = ["today", "week", "72h"] as const;
type Range = (typeof ranges)[number];
const range = ref<Range>("today");

const clockQuery = useQuery({ queryKey: ["runtime-clock"], queryFn: () => runtimeApi.clock(), refetchInterval: 60_000 });
const eventsQuery = useQuery({
  queryKey: ["overview", "all"],
  queryFn: () => eventApi.list({ includeReminders: true, includeCourseTemplates: false }),
});
const timezone = computed(() => clockQuery.data.value?.timezone || "Asia/Shanghai");
const now = computed(() => {
  const raw = clockQuery.data.value?.serverNow;
  const parsed = raw ? new Date(raw) : new Date();
  return Number.isFinite(parsed.getTime()) ? parsed : new Date();
});
function dateInZone(value: Date): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: timezone.value, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(value);
  const map = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${map.year}-${map.month}-${map.day}`;
}
const today = computed(() => dateInZone(now.value));
function eventDay(event: SmartCoreEvent): string {
  const primary = getEventPrimaryTime(event);
  if (!primary) return "";
  const parsed = new Date(primary.includes("T") ? primary : `${primary}T12:00:00`);
  return Number.isFinite(parsed.getTime()) ? dateInZone(parsed) : "";
}
const active = computed(() => (eventsQuery.data.value ?? []).filter((event) => event.stat !== "cancelled"));
const todayEvents = computed(() => sortEvents(active.value.filter((event) => eventDay(event) === today.value)));
const rangeEvents = computed(() => {
  if (range.value === "today") return todayEvents.value;
  const start = range.value === "72h" ? now.value.getTime() : new Date(`${today.value}T00:00:00`).getTime();
  const end = range.value === "72h" ? start + 72 * 60 * 60 * 1000 : new Date(`${addDays(today.value, 7)}T00:00:00`).getTime();
  return sortEvents(active.value.filter((event) => {
    const time = new Date(getEventPrimaryTime(event)).getTime();
    return Number.isFinite(time) && time >= start && time < end;
  }));
});
const todayTodo = computed(() => todayEvents.value.filter((event) => event.stat === "todo").length);
const todayDone = computed(() => todayEvents.value.filter((event) => event.stat === "done").length);
const upcoming72h = computed(() => {
  const start = now.value.getTime();
  const end = start + 72 * 60 * 60 * 1000;
  return active.value.filter((event) => {
    if (event.stat !== "todo") return false;
    const time = new Date(getEventPrimaryTime(event)).getTime();
    return Number.isFinite(time) && time >= start && time <= end;
  }).length;
});
const nextAction = computed(() => todayEvents.value.find((event) => event.stat === "todo") ?? null);
const clockLabel = computed(() => {
  const raw = clockQuery.data.value?.serverNow;
  if (!raw) return t("overview.clockLoading");
  return new Intl.DateTimeFormat(locale.value === "en-US" ? "en-US" : "zh-CN", { month: "short", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: timezone.value }).format(new Date(raw));
});

const statusMutation = useMutation({
  mutationFn: ({ event, stat }: { event: SmartCoreEvent; stat: "todo" | "done" }) => eventApi.update(event.evtId, { stat }),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: ["overview"] });
    await queryClient.invalidateQueries({ queryKey: ["schedule"] });
    await queryClient.invalidateQueries({ queryKey: ["events"] });
  },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
function openEvent(event: SmartCoreEvent): void {
  void router.push({ name: "update", query: { date: eventDateKey(event), evtId: event.evtId } });
}
</script>

<template>
  <div class="m-overview">
    <section class="m-overview__summary card">
      <span class="m-overview__clock">{{ clockLabel }}</span>
      <div class="m-overview__stats">
        <div><strong>{{ todayTodo }}</strong><span>{{ t("overview.mobileTodo") }}</span></div>
        <div><strong>{{ todayDone }}</strong><span>{{ t("overview.mobileDone") }}</span></div>
        <div><strong>{{ upcoming72h }}</strong><span>{{ t("overview.mobileNext72h") }}</span></div>
      </div>
      <button v-if="nextAction" class="m-overview__next" type="button" @click="openEvent(nextAction)">
        <Sparkles :size="16" aria-hidden="true" />
        <span>{{ t("overview.nextAction") }}</span>
        <strong>{{ nextAction.title }}</strong>
      </button>
    </section>

    <section class="m-overview__schedule card">
      <div class="m-overview__tabs" role="tablist" :aria-label="t('schedule.rangeLabel')">
        <button
          v-for="item in ranges"
          :key="item"
          class="m-overview__tab"
          :class="{ 'm-overview__tab--active': range === item }"
          type="button"
          role="tab"
          :aria-selected="range === item"
          @click="range = item"
        >
          {{ t(`schedule.${item}`) }}
        </button>
      </div>
      <div v-if="eventsQuery.isPending.value" class="empty-state">{{ t("common.loading") }}</div>
      <div v-else-if="eventsQuery.isError.value" class="m-overview__error">
        {{ t("schedule.error") }}
        <button class="button" type="button" @click="eventsQuery.refetch()">{{ t("common.retry") }}</button>
      </div>
      <div v-else class="m-overview__list">
        <article v-for="event in rangeEvents" :key="event.evtId" class="m-overview__item">
          <button
            class="m-overview__toggle"
            type="button"
            :aria-label="event.stat === 'done' ? t('event.action.markTodo') : t('event.action.markDone')"
            :disabled="statusMutation.isPending.value"
            @click="statusMutation.mutate({ event, stat: event.stat === 'done' ? 'todo' : 'done' })"
          >
            <span :class="{ 'm-overview__check--done': event.stat === 'done' }">{{ event.stat === "done" ? "✓" : "" }}</span>
          </button>
          <EventCard :event="event" @select="openEvent" />
        </article>
        <EmptyState v-if="!rangeEvents.length" :text="t('schedule.empty')" />
      </div>
    </section>

    <RouterLink class="m-overview__add" :to="{ name: 'add' }" :aria-label="t('overview.addEvent')"><Plus :size="20" aria-hidden="true" /></RouterLink>
  </div>
</template>

<style scoped>
.m-overview {
  display: grid;
  gap: 12px;
  min-width: 0;
}
.m-overview__summary {
  display: grid;
  gap: 12px;
  padding: 14px;
}
.m-overview__clock {
  color: var(--color-text-muted);
  font-size: 13px;
}
.m-overview__stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.m-overview__stats div {
  display: grid;
  gap: 2px;
  padding: 10px 8px;
  border-radius: 10px;
  background: #f8fafc;
  text-align: center;
}
.m-overview__stats strong {
  font-size: 22px;
  line-height: 1.1;
}
.m-overview__stats span {
  color: var(--color-text-muted);
  font-size: 12px;
}
.m-overview__next {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  min-height: 44px;
  padding: 10px 12px;
  border: 0;
  border-radius: 10px;
  background: #eff6ff;
  color: #1d4ed8;
  font: inherit;
  text-align: left;
}
.m-overview__next span {
  flex: 0 0 auto;
  font-size: 12px;
  font-weight: 700;
}
.m-overview__next strong {
  min-width: 0;
  overflow: hidden;
  color: var(--color-text);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-overview__schedule {
  overflow: hidden;
}
.m-overview__tabs {
  display: flex;
  gap: 6px;
  padding: 10px;
  border-bottom: 1px solid var(--border-color);
  overflow-x: auto;
}
.m-overview__tab {
  flex: 1 0 auto;
  min-height: 38px;
  padding: 7px 12px;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  background: #fff;
  color: var(--color-text-muted);
  font: inherit;
  font-size: 14px;
  white-space: nowrap;
}
.m-overview__tab--active {
  border-color: #93c5fd;
  background: #eff6ff;
  color: #1d4ed8;
}
.m-overview__list {
  display: grid;
  gap: 8px;
  padding: 10px;
}
.m-overview__item {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  align-items: start;
  gap: 8px;
}
.m-overview__item :deep(.event-card) {
  min-width: 0;
  padding: 12px;
}
.m-overview__toggle {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  margin-top: 6px;
  border: 1px solid var(--border-color);
  border-radius: 50%;
  background: #fff;
}
.m-overview__toggle span {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  color: transparent;
}
.m-overview__check--done {
  background: #16a34a;
  color: #fff !important;
}
.m-overview__error {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 28px 12px;
  color: var(--color-danger);
}
.m-overview__add {
  position: fixed;
  right: 16px;
  bottom: calc(var(--mobile-tabbar-height, 0px) + 16px);
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: #2563eb;
  color: #fff;
  box-shadow: 0 10px 22px rgb(37 99 235 / 28%);
  z-index: 22;
}
</style>
