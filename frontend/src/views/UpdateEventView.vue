<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import PageHeader from "@/components/base/PageHeader.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import PreviewActionButton from "@/components/base/PreviewActionButton.vue";
import EventCard from "@/components/events/EventCard.vue";
import EventEditor from "@/components/events/EventEditor.vue";
import EventPreviewCard from "@/components/events/EventPreviewCard.vue";
import { eventApi } from "@/api/event";
import { useToast } from "@/composables/useToast";
import type { DdlPlan, SmartCoreEvent } from "@/types/event";
import { addDays, eventDateKey, extractDateQuery, getEventPrimaryTime, todayKey } from "@/utils/date";
import { matchesEventSearch, sortEvents } from "@/utils/event";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const toast = useToast();
const queryClient = useQueryClient();
const date = ref(String(route.query.date ?? todayKey()));
const text = ref(String(route.query.q ?? ""));
const status = ref<"all" | "active" | "cancelled">((String(route.query.stat ?? "active") as "all" | "active" | "cancelled"));
const selected = ref<SmartCoreEvent | null>(null);
const editing = ref(false);
const directId = computed(() => String(route.query.evtId ?? route.query.event ?? ""));
let pendingEventId = "";
let pendingEventRequest: Promise<SmartCoreEvent> | null = null;

const eventsQuery = useQuery({
  queryKey: computed(() => ["events", "day", date.value]),
  queryFn: () => eventApi.list({ date: date.value, includeReminders: true, includeCourseTemplates: false }),
});

const filtered = computed(() => sortEvents((eventsQuery.data.value ?? [])
  .filter((event) => {
    if (status.value === "all") return true;
    if (status.value === "active") return event.stat === "todo" || event.stat === "done";
    return event.stat === "cancelled";
  })
  .filter((event) => matchesEventSearch(event, text.value))));
const selectedPlans = computed<DdlPlan[]>(() => selected.value?.evtType === "ddl" ? selected.value.plans ?? [] : []);
const selectedDuration = computed(() => selected.value?.evtType === "plan" ? selected.value.durationMin : null);
const selectedHardDdl = computed(() => selected.value?.evtType === "ddl" && selected.value.hardDdl);
const selectedLocation = computed(() => selected.value?.evtType === "course" ? selected.value.location ?? "" : "");
const selectedTeacher = computed(() => selected.value?.evtType === "course" ? selected.value.teacher ?? "" : "");
const selectedSchedule = computed(() => selected.value?.evtType === "course"
  ? t("course.scheduleSummary", { start: selected.value.stTime, end: selected.value.endTime, startWeek: selected.value.startWeek, endWeek: selected.value.endWeek })
  : "");

watch(text, (value) => {
  const found = extractDateQuery(value);
  if (found && found !== date.value) date.value = found;
});

watch([date, text, status], () => {
  void router.replace({ query: { date: date.value, q: text.value || undefined, stat: status.value === "active" ? undefined : status.value, evtId: selected.value?.evtId || undefined } });
});

watch(selected, (event) => {
  if (!event) return;
  void router.replace({ query: { ...route.query, date: date.value, stat: undefined, evtId: event.evtId, event: undefined } });
});

async function openDirectEvent() {
  if (!directId.value || selected.value?.evtId === directId.value) return;
  try {
    const event = await eventApi.read(directId.value);
    selected.value = event;
    editing.value = false;
    const eventDate = eventDateKey(event);
    if (eventDate !== date.value) date.value = eventDate;
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function loadEvent(event: SmartCoreEvent) {
  if (selected.value?.evtId === event.evtId) return selected.value;
  if (pendingEventId === event.evtId && pendingEventRequest) return pendingEventRequest;
  pendingEventId = event.evtId;
  pendingEventRequest = eventApi.read(event.evtId);
  try {
    return await pendingEventRequest;
  } finally {
    pendingEventId = "";
    pendingEventRequest = null;
  }
}

async function selectEvent(event: SmartCoreEvent) {
  editing.value = false;
  try {
    selected.value = await loadEvent(event);
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function editEvent(event: SmartCoreEvent) {
  try {
    selected.value = await loadEvent(event);
    editing.value = true;
  } catch (error) {
    editing.value = false;
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

onMounted(() => { void openDirectEvent(); });
watch(directId, () => { void openDirectEvent(); });
watch([filtered, directId], ([events, eventId]) => {
  if (eventId || editing.value || !events.length) return;
  const current = events.find((event) => event.evtId === selected.value?.evtId);
  if (!current) void selectEvent(events[0]!);
}, { immediate: true });

const updateMutation = useMutation({
  mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) => eventApi.update(id, payload),
  onSuccess: async (event) => { selected.value = event; editing.value = false; toast.success(t("event.updated")); await queryClient.invalidateQueries({ queryKey: ["events"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const cancelMutation = useMutation({
  mutationFn: (id: string) => eventApi.cancel(id),
  onSuccess: async () => { toast.success(t("event.cancelled")); selected.value = null; editing.value = false; await queryClient.invalidateQueries({ queryKey: ["events"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const busy = computed(() => updateMutation.isPending.value || cancelMutation.isPending.value);

function move(days: number) { selected.value = null; editing.value = false; date.value = addDays(date.value, days); }
function markDone() { if (selected.value) updateMutation.mutate({ id: selected.value.evtId, payload: { stat: "done" } }); }
</script>

<template>
  <div class="dual-scroll-page">
    <PageHeader :title="t('update.title')" :subtitle="t('update.subtitle')" />
    <section class="date-toolbar"><button class="button" @click="move(-1)">{{ t("common.previous") }}</button><input v-model="date" type="date" /><button class="button" @click="date = todayKey()">{{ t("common.today") }}</button><button class="button" @click="move(1)">{{ t("common.next") }}</button><input v-model="text" :placeholder="t('common.search')" /><select v-model="status"><option value="all">{{ t("common.all") }}</option><option value="active">{{ t("event.status.active") }}</option><option value="cancelled">{{ t("event.status.cancelled") }}</option></select></section>
    <section class="split-scroll-layout split-scroll-layout--update">
      <div class="split-scroll-column split-scroll-column--main" data-staged-wheel-scroll>
        <BaseCard :title="`${t('update.events')} · ${filtered.length}`"><div class="idea-cards event-list"><EventCard v-for="event in filtered" :key="event.evtId" :event="event" :selected="selected?.evtId === event.evtId" @select="selectEvent" @edit="editEvent" /><div v-if="eventsQuery.isPending.value" class="empty-state">{{ t("common.loading") }}</div><EmptyState v-else-if="!filtered.length" /></div></BaseCard>
      </div>
      <aside class="split-scroll-column split-scroll-column--side" data-staged-wheel-scroll>
        <div class="stack">
          <BaseCard v-if="selected && !editing" :title="t('preview.title')">
            <template #actions><PreviewActionButton :label="t('common.edit')" @click="editing = true" /></template>
            <EventPreviewCard
              :type="selected.evtType"
              :title="selected.title"
              :description="selected.desc"
              :priority="selected.prio"
              :status="selected.stat"
              :time="getEventPrimaryTime(selected)"
              :duration-min="selectedDuration"
              :hard-ddl="selectedHardDdl"
              :plans="selectedPlans"
              :location="selectedLocation"
              :teacher="selectedTeacher"
              :schedule="selectedSchedule"
            />
          </BaseCard>
          <BaseCard v-else-if="selected" :title="t('update.editor')">
            <template #actions><PreviewActionButton action="close" :label="t('common.close')" @click="editing = false" /></template>
            <EventEditor :event="selected" :busy="busy" @save="updateMutation.mutate({ id: selected!.evtId, payload: $event })" @done="markDone" @cancel="cancelMutation.mutate(selected!.evtId)" />
          </BaseCard>
          <BaseCard v-else><EmptyState :text="t('update.select')" /></BaseCard>
        </div>
      </aside>
    </section>
  </div>
</template>
