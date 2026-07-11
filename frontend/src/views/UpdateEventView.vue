<script setup lang="ts">
import { computed, ref, watch } from "vue";
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
import { addDays, todayKey } from "@/utils/date";
import { sortEvents } from "@/utils/event";

const { t } = useI18n(); const route = useRoute(); const router = useRouter(); const toast = useToast(); const queryClient = useQueryClient();
const date = ref(String(route.query.date ?? todayKey())); const status = ref<EventStatus | "all">("all"); const text = ref(String(route.query.q ?? "")); const selected = ref<SmartCoreEvent | null>(null);
const eventsQuery = useQuery({ queryKey: computed(() => ["events", date.value, text.value]), queryFn: () => eventApi.list({ date: date.value, includeReminders: true, text: text.value || undefined }) });
const filtered = computed(() => sortEvents((eventsQuery.data.value ?? []).filter((event) => status.value === "all" || event.stat === status.value)));
watch(filtered, (events) => { const wanted = String(route.query.event ?? ""); selected.value = events.find((event) => event.evtId === wanted) ?? (selected.value ? events.find((event) => event.evtId === selected.value?.evtId) ?? null : null); }, { immediate: true });
watch([date, text], () => void router.replace({ query: { ...route.query, date: date.value, q: text.value || undefined } }));
const updateMutation = useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) => eventApi.update(id, payload), onSuccess: async (event) => { selected.value = event; toast.success(t("event.updated")); await queryClient.invalidateQueries({ queryKey: ["events"] }); } });
const cancelMutation = useMutation({ mutationFn: (id: string) => eventApi.cancel(id), onSuccess: async () => { toast.success(t("event.cancelled")); selected.value = null; await queryClient.invalidateQueries({ queryKey: ["events"] }); } });
function move(days: number) { date.value = addDays(date.value, days); }
</script>
<template>
  <section class="page-heading"><div><h1>{{ t("update.title") }}</h1><p>{{ t("update.subtitle") }}</p></div></section>
  <section class="date-toolbar"><button class="button" @click="move(-1)">{{ t("common.previous") }}</button><input v-model="date" type="date" /><button class="button" @click="date = todayKey()">{{ t("common.today") }}</button><button class="button" @click="move(1)">{{ t("common.next") }}</button><input v-model="text" :placeholder="t('common.search')" /><select v-model="status"><option value="all">{{ t("common.all") }}</option><option value="todo">{{ t("event.status.todo") }}</option><option value="done">{{ t("event.status.done") }}</option><option value="cancelled">{{ t("event.status.cancelled") }}</option></select></section>
  <section class="editor-layout"><BaseCard :title="t('update.events')"><div class="event-list"><EventCard v-for="event in filtered" :key="event.evtId" :event="event" :selected="selected?.evtId === event.evtId" @select="selected = $event" /><EmptyState v-if="!filtered.length" /></div></BaseCard><BaseCard :title="t('update.editor')"><EventEditor v-if="selected" :event="selected" @save="updateMutation.mutate({ id: selected!.evtId, payload: $event })" @cancel="cancelMutation.mutate(selected!.evtId)" /><EmptyState v-else :text="t('update.select')" /></BaseCard></section>
</template>
