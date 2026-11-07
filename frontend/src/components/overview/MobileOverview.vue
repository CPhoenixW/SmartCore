<script setup lang="ts">
import { computed, ref } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import EmptyState from "@/components/base/EmptyState.vue";
import { eventApi } from "@/api/event";
import { runtimeApi } from "@/api/runtime";
import { useToast } from "@/composables/useToast";
import type { SmartCoreEvent } from "@/types/event";
import { addDays, getEventPrimaryTime } from "@/utils/date";
import { sortEvents } from "@/utils/event";

const { t, locale } = useI18n();
const router = useRouter();
const toast = useToast();
const queryClient = useQueryClient();
const note = ref("");
const laterOpen = ref(false);

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
const tomorrow = computed(() => addDays(today.value, 1));
const dayAfter = computed(() => addDays(today.value, 2));
function eventInstant(event: SmartCoreEvent): number {
  const primary = getEventPrimaryTime(event);
  if (!primary) return Number.NaN;
  const parsed = new Date(primary.includes("T") ? primary : `${primary}T12:00:00`);
  return parsed.getTime();
}
function eventDay(event: SmartCoreEvent): string {
  const time = eventInstant(event);
  return Number.isFinite(time) ? dateInZone(new Date(time)) : "";
}
function clockTime(event: SmartCoreEvent): string {
  const time = eventInstant(event);
  if (!Number.isFinite(time)) return "";
  return new Intl.DateTimeFormat(locale.value === "en-US" ? "en-US" : "zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: timezone.value,
  }).format(new Date(time));
}
const active = computed(() => (eventsQuery.data.value ?? []).filter((event) => event.stat !== "cancelled" && (event.evtType === "plan" || event.evtType === "remind")));
const upcoming = computed(() => sortEvents(active.value.filter((event) => event.stat === "todo" && eventInstant(event) >= now.value.getTime() - 60_000)));
const nextAction = computed(() => upcoming.value[0] ?? null);
const todayRest = computed(() => sortEvents(active.value.filter((event) => event.stat === "todo" && event.evtId !== nextAction.value?.evtId && eventDay(event) === today.value)));
const tomorrowCount = computed(() => active.value.filter((event) => event.stat === "todo" && eventDay(event) === tomorrow.value).length);
const dayAfterCount = computed(() => active.value.filter((event) => event.stat === "todo" && eventDay(event) === dayAfter.value).length);
const laterEvents = computed(() => sortEvents(active.value.filter((event) => event.stat === "todo" && eventDay(event) > today.value)));
const clockLabel = computed(() => {
  const raw = clockQuery.data.value?.serverNow;
  if (!raw) return t("overview.clockLoading");
  return new Intl.DateTimeFormat(locale.value === "en-US" ? "en-US" : "zh-CN", {
    month: "short",
    day: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: timezone.value,
  }).format(new Date(raw));
});
const soonLabel = computed(() => {
  const event = nextAction.value;
  if (!event) return "";
  const minutes = Math.round((eventInstant(event) - now.value.getTime()) / 60_000);
  if (minutes <= 0) return t("overview.now");
  if (minutes < 60) return t("overview.inMinutes", { count: minutes });
  const hours = Math.floor(minutes / 60);
  return t("overview.inHours", { count: hours });
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
  void router.push({ name: "assistant", query: { prompt: event.title } });
}
function ask(): void {
  const text = note.value.trim();
  if (!text) return;
  note.value = "";
  void router.push({ name: "assistant", query: { prompt: text } });
}
</script>

<template>
  <div class="m-overview">
    <p class="m-overview__clock">{{ clockLabel }}</p>

    <section v-if="nextAction" class="m-overview__next card">
      <div class="m-overview__next-top">
        <span>{{ t("overview.nextAction") }}</span>
        <strong>{{ clockTime(nextAction) }}</strong>
        <em>{{ t(`event.type.${nextAction.evtType}`) }}</em>
      </div>
      <h2>{{ nextAction.title }}</h2>
      <p>{{ soonLabel }}</p>
      <div class="m-overview__actions">
        <button class="button button--primary" type="button" :disabled="statusMutation.isPending.value" @click="statusMutation.mutate({ event: nextAction, stat: 'done' })">{{ t("event.status.done") }}</button>
        <button class="button" type="button" @click="openEvent(nextAction)">{{ t("common.open") }}</button>
      </div>
    </section>

    <section class="card m-overview__day">
      <h2>{{ t("overview.restOfDay") }}</h2>
      <div v-if="eventsQuery.isPending.value" class="empty-state">{{ t("common.loading") }}</div>
      <div v-else-if="eventsQuery.isError.value" class="m-overview__error">
        {{ t("schedule.error") }}
        <button class="button" type="button" @click="eventsQuery.refetch()">{{ t("common.retry") }}</button>
      </div>
      <ol v-else-if="todayRest.length" class="m-overview__timeline">
        <li v-for="event in todayRest" :key="event.evtId">
          <time>{{ clockTime(event) }}</time>
          <button type="button" @click="openEvent(event)">
            <strong>{{ event.title }}</strong>
            <small>{{ t(`event.type.${event.evtType}`) }}</small>
          </button>
        </li>
      </ol>
      <EmptyState v-else :text="t('schedule.empty')" />
    </section>

    <section class="card m-overview__later">
      <button type="button" @click="laterOpen = !laterOpen">
        <span>{{ t("overview.later") }}</span>
        <strong>{{ t("overview.laterCounts", { tomorrow: tomorrowCount, dayAfter: dayAfterCount }) }}</strong>
        <small>{{ laterOpen ? "−" : "+" }}</small>
      </button>
      <ol v-if="laterOpen && laterEvents.length" class="m-overview__timeline">
        <li v-for="event in laterEvents" :key="event.evtId">
          <time>{{ clockTime(event) }}</time>
          <button type="button" @click="openEvent(event)">
            <strong>{{ event.title }}</strong>
            <small>{{ eventDay(event) }} · {{ t(`event.type.${event.evtType}`) }}</small>
          </button>
        </li>
      </ol>
    </section>

    <form class="natural-input card" @submit.prevent="ask">
      <textarea v-model="note" rows="2" :placeholder="t('overview.askPlaceholder')" />
      <button class="button button--primary" type="submit" :disabled="!note.trim()">{{ t("overview.askAssistant") }}</button>
    </form>
  </div>
</template>

<style scoped>
.m-overview { display: grid; gap: 12px; min-width: 0; }
.m-overview__clock { margin: 0; color: var(--color-text-muted); font-size: 13px; }
.m-overview__next, .m-overview__day, .m-overview__later { padding: 14px; }
.m-overview__next { display: grid; gap: 6px; background: #eff6ff; }
.m-overview__next-top { display: flex; align-items: center; gap: 8px; color: #1d4ed8; font-size: 13px; }
.m-overview__next-top strong { color: var(--color-text); font-size: 15px; }
.m-overview__next-top em { margin-left: auto; font-style: normal; }
.m-overview__next h2, .m-overview__day h2 { margin: 0; font-size: 20px; }
.m-overview__next p { margin: 0; color: var(--color-text-muted); font-size: 13px; }
.m-overview__actions { display: flex; gap: 8px; margin-top: 6px; }
.m-overview__day h2 { margin-bottom: 8px; font-size: 16px; }
.m-overview__timeline { display: grid; margin: 0; padding: 0; list-style: none; }
.m-overview__timeline li { display: grid; grid-template-columns: 52px minmax(0, 1fr); gap: 8px; align-items: center; padding: 10px 0; border-top: 1px solid var(--border-color); }
.m-overview__timeline time { color: var(--color-text-muted); font-size: 13px; }
.m-overview__timeline button { display: grid; gap: 2px; min-width: 0; padding: 0; border: 0; background: transparent; text-align: left; font: inherit; }
.m-overview__timeline strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.m-overview__timeline small { color: var(--color-text-muted); font-size: 12px; }
.m-overview__later button { display: flex; align-items: baseline; gap: 8px; width: 100%; padding: 0; border: 0; background: transparent; text-align: left; font: inherit; }
.m-overview__later span, .m-overview__later small { color: var(--color-text-muted); font-size: 13px; }
.m-overview__later strong { flex: 1; font-size: 14px; font-weight: 600; }
.m-overview__error { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 20px 0; color: var(--color-danger); }
.natural-input { display: grid; gap: 10px; padding: 12px; }
.natural-input textarea { width: 100%; min-height: 64px; padding: 10px 12px; border: 1px solid var(--border-color); border-radius: 10px; font: inherit; resize: none; }
</style>
