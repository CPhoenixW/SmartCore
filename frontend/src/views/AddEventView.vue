<script setup lang="ts">
import { computed, ref } from "vue";
import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import DdlForm from "@/components/events/DdlForm.vue";
import PlanForm from "@/components/events/PlanForm.vue";
import ReminderForm from "@/components/events/ReminderForm.vue";
import { aiApi } from "@/api/ai";
import { eventApi } from "@/api/event";
import { useToast } from "@/composables/useToast";
import type { CreateDdlPayload, CreatePlanPayload, CreateReminderPayload, EventType } from "@/types/event";

const { t } = useI18n(); const toast = useToast(); const queryClient = useQueryClient();
const active = ref<Exclude<EventType, "course">>("plan"); const natural = ref(""); const parsed = ref<Record<string, unknown>>({});
const createMutation = useMutation({ mutationFn: async (payload: CreatePlanPayload | CreateReminderPayload | CreateDdlPayload) => active.value === "plan" ? eventApi.createPlan(payload as CreatePlanPayload) : active.value === "remind" ? eventApi.createReminder(payload as CreateReminderPayload) : eventApi.createDdl(payload as CreateDdlPayload), onSuccess: async () => { toast.success(t("event.created")); await queryClient.invalidateQueries({ queryKey: ["events"] }); } });
const parseMutation = useMutation({ mutationFn: () => aiApi.parse(natural.value), onSuccess: (data) => { parsed.value = data; const type = String(data.evtType ?? data.tab ?? "plan"); active.value = type === "ddl" ? "ddl" : type === "remind" ? "remind" : "plan"; toast.success(t("add.parsed")); }, onError: (error) => toast.error(String(error)) });
const planInitial = computed(() => parsed.value as Partial<CreatePlanPayload>); const reminderInitial = computed(() => parsed.value as Partial<CreateReminderPayload>); const ddlInitial = computed(() => parsed.value as Partial<CreateDdlPayload>);
</script>
<template>
  <section class="page-heading"><div><h1>{{ t("add.title") }}</h1><p>{{ t("add.subtitle") }}</p></div></section>
  <section class="form-layout">
    <div class="stack">
      <BaseCard :title="t('add.natural')"><div class="natural-input"><textarea v-model="natural" rows="3" :placeholder="t('add.placeholder')" /><button class="button button--primary" type="button" :disabled="!natural.trim() || parseMutation.isPending.value" @click="parseMutation.mutate()">{{ t("add.parse") }}</button></div></BaseCard>
      <BaseCard><div class="tabs"><button v-for="type in ['plan','remind','ddl']" :key="type" class="tab" :class="{ 'tab--active': active === type }" type="button" @click="active = type as typeof active">{{ t(`event.type.${type}`) }}</button></div>
        <PlanForm v-if="active === 'plan'" :initial="planInitial" @submit="createMutation.mutate" />
        <ReminderForm v-else-if="active === 'remind'" :initial="reminderInitial" @submit="createMutation.mutate" />
        <DdlForm v-else :initial="ddlInitial" @submit="createMutation.mutate" />
      </BaseCard>
    </div>
    <BaseCard title="Create preview"><pre class="json-preview">{{ JSON.stringify(parsed, null, 2) }}</pre></BaseCard>
  </section>
</template>
