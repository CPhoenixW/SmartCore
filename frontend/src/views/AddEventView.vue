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
import type { CreateDdlPayload, CreatePlanPayload, CreateReminderPayload } from "@/types/event";
import { defaultDdlPlans } from "@/utils/date";

type CreateType = "plan" | "remind" | "ddl";
type CreatePayload = CreatePlanPayload | CreateReminderPayload | CreateDdlPayload;

const { t } = useI18n();
const toast = useToast();
const queryClient = useQueryClient();
const active = ref<CreateType>("plan");
const natural = ref("");
const parsed = ref<Record<string, unknown>>({});
const formKey = ref(0);

async function createEvent(payload: CreatePayload) {
  if (active.value === "plan") return eventApi.createPlan(payload as CreatePlanPayload);
  if (active.value === "remind") return eventApi.createReminder(payload as CreateReminderPayload);
  return eventApi.createDdl(payload as CreateDdlPayload);
}

const createMutation = useMutation({
  mutationFn: createEvent,
  onSuccess: async () => {
    toast.success(t("event.created"));
    parsed.value = {};
    natural.value = "";
    formKey.value += 1;
    await queryClient.invalidateQueries({ queryKey: ["events"] });
  },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});

const parseMutation = useMutation({
  mutationFn: () => aiApi.parse<Record<string, unknown>>(natural.value),
  onSuccess: (data) => {
    parsed.value = data;
    const type = String(data.evtType ?? data.tab ?? "plan");
    active.value = type === "ddl" ? "ddl" : type === "remind" ? "remind" : "plan";
    formKey.value += 1;
    toast.success(t("add.parsed"));
  },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});

const planInitial = computed(() => parsed.value as Partial<CreatePlanPayload>);
const reminderInitial = computed(() => parsed.value as Partial<CreateReminderPayload>);
const ddlInitial = computed(() => parsed.value as Partial<CreateDdlPayload>);
const busy = computed(() => createMutation.isPending.value || parseMutation.isPending.value);

function applyTemplate(kind: "homework" | "plan" | "exam" | "project") {
  const now = Date.now();
  if (kind === "homework") {
    active.value = "ddl";
    const endTime = new Date(now + 2 * 86_400_000).toISOString();
    parsed.value = { title: "提交作业", desc: "", endTime, prio: "high", hardDdl: true, plans: defaultDdlPlans(endTime) };
  } else {
    active.value = "plan";
    const titles = { plan: "计划事项", exam: "考试复习", project: "项目跟进" };
    parsed.value = { title: titles[kind], desc: "", stTime: new Date(now + 3_600_000).toISOString(), durationMin: kind === "exam" ? 90 : 30, prio: kind === "project" ? "high" : "mid" };
  }
  formKey.value += 1;
}
</script>

<template>
  <section class="page-heading"><div><h1>{{ t("add.title") }}</h1><p>{{ t("add.subtitle") }}</p></div></section>
  <section class="form-layout">
    <div class="stack">
      <BaseCard :title="t('add.natural')"><div class="natural-input"><textarea v-model="natural" rows="3" :placeholder="t('add.placeholder')" /><button class="button button--primary" type="button" :disabled="!natural.trim() || busy" @click="parseMutation.mutate()">{{ t("add.parse") }}</button></div></BaseCard>
      <BaseCard>
        <div class="tabs"><button v-for="type in ['plan','remind','ddl']" :key="type" class="tab" :class="{ 'tab--active': active === type }" type="button" @click="active = type as CreateType">{{ t(`event.type.${type}`) }}</button></div>
        <PlanForm v-if="active === 'plan'" :key="`plan-${formKey}`" :initial="planInitial" @submit="createMutation.mutate" />
        <ReminderForm v-else-if="active === 'remind'" :key="`remind-${formKey}`" :initial="reminderInitial" @submit="createMutation.mutate" />
        <DdlForm v-else :key="`ddl-${formKey}`" :initial="ddlInitial" @submit="createMutation.mutate" />
      </BaseCard>
    </div>
    <div class="stack">
      <BaseCard title="常用模板"><div class="quick-grid"><button @click="applyTemplate('homework')">作业 DDL</button><button @click="applyTemplate('plan')">计划事项</button><button @click="applyTemplate('exam')">考试复习</button><button @click="applyTemplate('project')">项目跟进</button></div></BaseCard>
      <BaseCard title="Create preview"><pre class="json-preview">{{ JSON.stringify(parsed, null, 2) }}</pre></BaseCard>
    </div>
  </section>
</template>
