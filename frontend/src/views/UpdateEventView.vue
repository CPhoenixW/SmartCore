<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import EventCard from "@/components/events/EventCard.vue";
import EventEditor from "@/components/events/EventEditor.vue";
import { eventApi } from "@/api/event";
import { useToast } from "@/composables/useToast";
import type { EventStatus, SmartCoreEvent } from "@/types/event";
import { addDays, eventDateKey, extractDateQuery, todayKey } from "@/utils/date";
import { matchesEventSearch, sortEvents } from "@/utils/event";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const toast = useToast();
const queryClient = useQueryClient();
const date = ref(String(route.query.date ?? todayKey()));
const status = ref<EventStatus | "all">((String(route.query.stat ?? "todo") as EventStatus | "all"));
const text = ref(String(route.query.q ?? ""));
const selected = ref<SmartCoreEvent | null>(null);
const directId = computed(() => String(route.query.evtId ?? route.query.event ?? ""));

const eventsQuery = useQuery({
  queryKey: computed(() => ["events", "day", date.value]),
  queryFn: () => eventApi.list({ date: date.value, includeReminders: true, includeCourseTemplates: false }),
});

const filtered = computed(() => sortEvents((eventsQuery.data.value ?? [])
  .filter((event) => status.value === "all" || event.stat === status.value)
  .filter((event) => matchesEventSearch(event, text.value))));

watch(filtered, (events) => {
  if (selected.value) selected.value = events.find((event) => event.evtId === selected.value?.evtId) ?? selected.value;
}, { immediate: true });

watch(text, (value) => {
  const found = extractDateQuery(value);
  if (found && found !== date.value) date.value = found;
});

watch([date, text, status], () => {
  void router.replace({ query: { date: date.value, q: text.value || undefined, stat: status.value === "todo" ? undefined : status.value, evtId: selected.value?.evtId || undefined } });
});

watch(selected, (event) => {
  if (!event) return;
  void router.replace({ query: { ...route.query, date: date.value, evtId: event.evtId, event: undefined } });
});

async function openDirectEvent() {
  if (!directId.value) return;
  try {
    const event = await eventApi.read(directId.value);
    selected.value = event;
    const eventDate = eventDateKey(event);
    if (eventDate !== date.value) date.value = eventDate;
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

onMounted(() => { void openDirectEvent(); });
watch(directId, () => { void openDirectEvent(); });

const updateMutation = useMutation({
  mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) => eventApi.update(id, payload),
  onSuccess: async (event) => { selected.value = event; toast.success(t("event.updated")); await queryClient.invalidateQueries({ queryKey: ["events"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const cancelMutation = useMutation({
  mutationFn: (id: string) => eventApi.cancel(id),
  onSuccess: async () => { toast.success(t("event.cancelled")); selected.value = null; await queryClient.invalidateQueries({ queryKey: ["events"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const busy = computed(() => updateMutation.isPending.value || cancelMutation.isPending.value);

function move(days: number) { selected.value = null; date.value = addDays(date.value, days); }
function markDone() { if (selected.value) updateMutation.mutate({ id: selected.value.evtId, payload: { stat: "done" } }); }
</script>

<template>
  <section class="page-heading"><div><h1>{{ t("update.title") }}</h1><p>{{ t("update.subtitle") }}</p></div></section>
  <section class="date-toolbar"><button class="button" @click="move(-1)">{{ t("common.previous") }}</button><input v-model="date" type="date" /><button class="button" @click="date = todayKey()">{{ t("common.today") }}</button><button class="button" @click="move(1)">{{ t("common.next") }}</button><input v-model="text" :placeholder="t('common.search')" /><select v-model="status"><option value="all">{{ t("common.all") }}</option><option value="todo">{{ t("event.status.todo") }}</option><option value="done">{{ t("event.status.done") }}</option><option value="cancelled">{{ t("event.status.cancelled") }}</option></select></section>
  <section class="editor-layout">
    <BaseCard :title="`${t('update.events')} · ${filtered.length}`"><div class="event-list"><EventCard v-for="event in filtered" :key="event.evtId" :event="event" :selected="selected?.evtId === event.evtId" @select="selected = $event" /><div v-if="eventsQuery.isPending.value" class="empty-state">{{ t("common.loading") }}</div><EmptyState v-else-if="!filtered.length" /></div></BaseCard>
    <BaseCard :title="t('update.editor')"><EventEditor v-if="selected" :event="selected" :busy="busy" @save="updateMutation.mutate({ id: selected!.evtId, payload: $event })" @done="markDone" @cancel="cancelMutation.mutate(selected!.evtId)" /><EmptyState v-else :text="t('update.select')" /></BaseCard>
  </section>
</template>
