<script setup lang="ts">
import { computed } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { ArrowRight, Clock3, Plus, Sparkles } from "@lucide/vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import EventCard from "@/components/events/EventCard.vue";
import EventStatusToggle from "@/components/events/EventStatusToggle.vue";
import { eventApi } from "@/api/event";
import { runtimeApi } from "@/api/runtime";
import { ideaApi } from "@/api/idea";
import { useToast } from "@/composables/useToast";
import type { SmartCoreEvent } from "@/types/event";
import { eventDateKey, getEventPrimaryTime, todayKey } from "@/utils/date";
import { sortEvents } from "@/utils/event";

const { t, locale } = useI18n();
const router = useRouter();
const toast = useToast();
const queryClient = useQueryClient();
const clockQuery = useQuery({ queryKey: ["runtime-clock"], queryFn: () => runtimeApi.clock(), refetchInterval: 60_000 });
const serverDate = computed(() => clockQuery.data.value?.serverNow?.slice(0, 10) || todayKey());
const serverTimestamp = computed(() => {
  const value = clockQuery.data.value?.serverNow;
  const timestamp = value ? new Date(value).getTime() : Date.now();
  return Number.isFinite(timestamp) ? timestamp : Date.now();
});
const todayQuery = useQuery({
  queryKey: computed(() => ["overview", "today", serverDate.value]),
  queryFn: () => eventApi.list({ date: serverDate.value, includeReminders: true, includeCourseTemplates: false }),
});
const allEventsQuery = useQuery({ queryKey: ["overview", "all"], queryFn: () => eventApi.list({ includeReminders: true, includeCourseTemplates: false }) });
const ideasQuery = useQuery({ queryKey: ["ideas", "overview"], queryFn: ideaApi.list });
const activeToday = computed(() => sortEvents((todayQuery.data.value ?? []).filter((event) => event.stat !== "cancelled")));
const nextAction = computed(() => activeToday.value.find((event) => event.stat === "todo") ?? activeToday.value[0] ?? null);
const next72h = computed(() => {
  const start = serverTimestamp.value;
  const end = start + 72 * 60 * 60 * 1000;
  return sortEvents((allEventsQuery.data.value ?? []).filter((event) => {
    if (event.stat !== "todo") return false;
    const time = new Date(getEventPrimaryTime(event)).getTime();
    return Number.isFinite(time) && time >= start && time <= end;
  })).slice(0, 6);
});
const openIdeas = computed(() => (ideasQuery.data.value ?? []).filter((idea) => !idea.handled));
const statusMutation = useMutation({
  mutationFn: ({ event, stat }: { event: SmartCoreEvent; stat: "todo" | "done" }) => eventApi.update(event.evtId, { stat }),
  onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["overview"] }); await queryClient.invalidateQueries({ queryKey: ["events"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
function openEvent(event: SmartCoreEvent): void {
  void router.push({ name: "update", query: { date: eventDateKey(event), evtId: event.evtId } });
}
function formatServerTime(value?: string): string {
  if (!value) return t("overview.clockLoading");
  return new Intl.DateTimeFormat(locale.value === "en-US" ? "en-US" : "zh-CN", { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}
</script>

<template>
  <div class="overview-page">
    <section class="overview-focus card">
      <div class="overview-focus__header"><div><span class="eyebrow"><Clock3 :size="14" aria-hidden="true" />{{ t("overview.serverClock") }}</span><strong>{{ formatServerTime(clockQuery.data.value?.serverNow) }}</strong><small>{{ clockQuery.data.value?.timezone || t("overview.clockLoading") }}</small></div><RouterLink class="button button--ghost" :to="{ name: 'schedule' }">{{ t("overview.openSchedule") }}<ArrowRight :size="15" aria-hidden="true" /></RouterLink></div>
      <div class="overview-focus__action"><div class="overview-focus__icon"><Sparkles :size="20" aria-hidden="true" /></div><div><span>{{ t("overview.nextAction") }}</span><strong v-if="nextAction">{{ nextAction.title }}</strong><p v-if="nextAction">{{ nextAction.desc || t("preview.noDescription") }}</p><EmptyState v-else :text="t('overview.emptyToday')" /></div><RouterLink v-if="nextAction" class="button button--primary" :to="{ name: 'update', query: { date: eventDateKey(nextAction), evtId: nextAction.evtId } }">{{ t("common.open") }}</RouterLink></div>
    </section>
    <section class="overview-columns">
      <BaseCard :title="t('overview.todayList')">
        <div v-if="todayQuery.isPending.value" class="empty-state">{{ t("common.loading") }}</div>
        <div v-else class="overview-event-list">
          <div v-for="event in activeToday" :key="event.evtId" class="overview-event-row"><EventStatusToggle :status="event.stat" :busy="statusMutation.isPending.value" :mark-done-label="t('event.action.markDone')" :mark-todo-label="t('event.action.markTodo')" @change="statusMutation.mutate({ event, stat: $event })" /><EventCard :event="event" @select="openEvent" /></div>
          <EmptyState v-if="!activeToday.length" :text="t('overview.emptyToday')" />
        </div>
      </BaseCard>
      <BaseCard :title="t('overview.next72Title')"><div class="overview-event-list"><EventCard v-for="event in next72h" :key="event.evtId" :event="event" @select="openEvent" /><EmptyState v-if="!next72h.length" :text="t('overview.emptyDeadline')" /></div></BaseCard>
      <BaseCard :title="t('overview.inboxTitle')"><div class="overview-inbox"><RouterLink class="overview-inbox__row" :to="{ name: 'ideas' }"><span>{{ t("overview.openIdeas") }}</span><strong>{{ openIdeas.length }}</strong><ArrowRight :size="15" aria-hidden="true" /></RouterLink><RouterLink class="overview-inbox__row" :to="{ name: 'settings' }"><span>{{ t("overview.notifications") }}</span><span class="overview-inbox__muted">{{ t("overview.manageInSettings") }}</span><ArrowRight :size="15" aria-hidden="true" /></RouterLink></div></BaseCard>
    </section>
    <RouterLink class="overview-add" :to="{ name: 'add' }" :aria-label="t('overview.addEvent')"><Plus :size="20" aria-hidden="true" /></RouterLink>
  </div>
</template>

<style scoped>
.overview-page{display:grid;gap:18px}.overview-focus{padding:20px}.overview-focus__header{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.overview-focus__header>div{display:grid;gap:4px}.eyebrow{display:flex;align-items:center;gap:5px;color:var(--color-text-muted);font-size:12px}.overview-focus__header strong{font-size:26px}.overview-focus__header small{color:var(--color-text-muted)}.overview-focus__action{display:flex;align-items:center;gap:13px;margin-top:22px;padding:15px;border-radius:13px;background:#eff6ff}.overview-focus__action>div:nth-child(2){display:grid;min-width:0;gap:4px;flex:1}.overview-focus__icon{display:grid;place-items:center;width:40px;height:40px;border-radius:12px;background:#dbeafe;color:#1d4ed8}.overview-focus__action span{color:#1d4ed8;font-size:12px;font-weight:700}.overview-focus__action strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:17px}.overview-focus__action p{margin:0;overflow:hidden;color:var(--color-text-muted);text-overflow:ellipsis;white-space:nowrap}.overview-columns{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(260px,.9fr);gap:16px}.overview-columns>.card:last-child{grid-column:1/-1}.overview-event-list{display:grid;gap:10px}.overview-event-row{display:grid;grid-template-columns:32px minmax(0,1fr);align-items:start;gap:8px}.overview-event-row :deep(.event-card){min-width:0}.overview-inbox{display:grid;gap:8px}.overview-inbox__row{display:flex;align-items:center;gap:9px;min-height:44px;padding:9px 10px;border:1px solid var(--border-color);border-radius:10px;color:var(--color-text)}.overview-inbox__row span:first-child{flex:1}.overview-inbox__row strong{color:var(--color-primary)}.overview-inbox__muted{color:var(--color-text-muted);font-size:12px}.overview-add{position:fixed;right:24px;bottom:28px;display:grid;place-items:center;width:52px;height:52px;border-radius:50%;background:#2563eb;color:#fff;box-shadow:0 10px 22px rgb(37 99 235 / 28%);z-index:22}.overview-add:hover{background:#1d4ed8}@media(max-width:760px){.overview-focus{padding:16px}.overview-focus__header{align-items:stretch;flex-direction:column}.overview-focus__header strong{font-size:22px}.overview-focus__action{align-items:flex-start;flex-wrap:wrap}.overview-focus__action .button{width:100%;margin-left:53px}.overview-columns{grid-template-columns:1fr}.overview-columns>.card:last-child{grid-column:auto}.overview-add{right:16px;bottom:88px}}
</style>
