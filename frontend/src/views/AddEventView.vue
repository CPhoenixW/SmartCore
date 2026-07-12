<script setup lang="ts">
import { computed, ref } from "vue";
import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import DdlForm from "@/components/events/DdlForm.vue";
import EventPreviewCard from "@/components/events/EventPreviewCard.vue";
import PlanForm from "@/components/events/PlanForm.vue";
import ReminderForm from "@/components/events/ReminderForm.vue";
import { aiApi } from "@/api/ai";
import { eventApi } from "@/api/event";
import { useToast } from "@/composables/useToast";
import type { CreateDdlPayload, CreatePlanPayload, CreateReminderPayload, DdlPlan, Priority } from "@/types/event";
import { defaultDdlPlans } from "@/utils/date";

type CreateType = "plan" | "remind" | "ddl";
type CreatePayload = CreatePlanPayload | CreateReminderPayload | CreateDdlPayload;

const { t } = useI18n();
const toast = useToast();
const queryClient = useQueryClient();
const active = ref<CreateType>("plan");
const natural = ref("");
const parsed = ref<Record<string, unknown>>({});
const livePreview = ref<CreatePayload | null>(null);
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
    livePreview.value = null;
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
    livePreview.value = null;
    formKey.value += 1;
    toast.success(t("add.parsed"));
  },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});

const planInitial = computed(() => parsed.value as Partial<CreatePlanPayload>);
const reminderInitial = computed(() => parsed.value as Partial<CreateReminderPayload>);
const ddlInitial = computed(() => parsed.value as Partial<CreateDdlPayload>);
const busy = computed(() => createMutation.isPending.value || parseMutation.isPending.value);
const previewRecord = computed<Record<string, unknown>>(() => (livePreview.value ?? parsed.value) as Record<string, unknown>);
const previewTitle = computed(() => String(previewRecord.value.title ?? ""));
const previewDescription = computed(() => String(previewRecord.value.desc ?? ""));
const previewPriority = computed<Priority>(() => {
  const value = String(previewRecord.value.prio ?? "mid");
  return value === "low" || value === "high" ? value : "mid";
});
const previewTime = computed(() => String(
  active.value === "plan"
    ? previewRecord.value.stTime ?? ""
    : active.value === "remind"
      ? previewRecord.value.triggerTime ?? ""
      : previewRecord.value.endTime ?? "",
));
const previewDuration = computed(() => active.value === "plan" ? Number(previewRecord.value.durationMin ?? 30) : null);
const previewPlans = computed<DdlPlan[]>(() => Array.isArray(previewRecord.value.plans) ? previewRecord.value.plans as DdlPlan[] : []);

function selectType(type: CreateType) {
  active.value = type;
  parsed.value = {};
  livePreview.value = null;
  formKey.value += 1;
}

function applyTemplate(kind: "homework" | "plan" | "exam" | "project") {
  const now = Date.now();
  if (kind === "homework") {
    active.value = "ddl";
    const endTime = new Date(now + 2 * 86_400_000).toISOString();
    parsed.value = { title: t("templates.homeworkTitle"), desc: "", endTime, prio: "high", hardDdl: true, plans: defaultDdlPlans(endTime) };
  } else {
    active.value = "plan";
    const titles = { plan: t("templates.planTitle"), exam: t("templates.examTitle"), project: t("templates.projectTitle") };
    parsed.value = { title: titles[kind], desc: "", stTime: new Date(now + 3_600_000).toISOString(), durationMin: kind === "exam" ? 90 : 30, prio: kind === "project" ? "high" : "mid" };
  }
  livePreview.value = null;
  formKey.value += 1;
}
</script>

<template>
  <div class="dual-scroll-page">
    <section class="page-heading"><div><h1>{{ t("add.title") }}</h1><p>{{ t("add.subtitle") }}</p></div></section>
    <section class="split-scroll-layout">
      <div class="split-scroll-column split-scroll-column--main">
        <div class="stack">
          <BaseCard :title="t('add.natural')"><div class="natural-input"><textarea v-model="natural" rows="3" :placeholder="t('add.placeholder')" /><button class="button button--primary" type="button" :disabled="!natural.trim() || busy" @click="parseMutation.mutate()">{{ t("add.parse") }}</button></div></BaseCard>
          <BaseCard :title="t('add.formTitle')">
            <div class="tabs"><button v-for="type in ['plan','remind','ddl']" :key="type" class="tab" :class="{ 'tab--active': active === type }" type="button" @click="selectType(type as CreateType)">{{ t(`event.type.${type}`) }}</button></div>
            <PlanForm v-if="active === 'plan'" :key="`plan-${formKey}`" :initial="planInitial" :busy="busy" @preview="livePreview = $event" @submit="createMutation.mutate" />
            <ReminderForm v-else-if="active === 'remind'" :key="`remind-${formKey}`" :initial="reminderInitial" :busy="busy" @preview="livePreview = $event" @submit="createMutation.mutate" />
            <DdlForm v-else :key="`ddl-${formKey}`" :initial="ddlInitial" :busy="busy" @preview="livePreview = $event" @submit="createMutation.mutate" />
          </BaseCard>
        </div>
      </div>
      <aside class="split-scroll-column split-scroll-column--side">
        <div class="stack">
          <BaseCard :title="t('preview.title')">
            <EventPreviewCard
              :type="active"
              :title="previewTitle"
              :description="previewDescription"
              :priority="previewPriority"
              :time="previewTime"
              :duration-min="previewDuration"
              :hard-ddl="Boolean(previewRecord.hardDdl)"
              :plans="previewPlans"
            />
          </BaseCard>
          <BaseCard :title="t('templates.title')"><div class="quick-grid"><button @click="applyTemplate('homework')">{{ t("templates.homework") }}</button><button @click="applyTemplate('plan')">{{ t("templates.plan") }}</button><button @click="applyTemplate('exam')">{{ t("templates.exam") }}</button><button @click="applyTemplate('project')">{{ t("templates.project") }}</button></div></BaseCard>
        </div>
      </aside>
    </section>
  </div>
</template>
