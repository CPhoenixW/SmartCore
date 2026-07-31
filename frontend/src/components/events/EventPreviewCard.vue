<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import type { DdlPlan, EventStatus, EventType, Priority } from "@/types/event";
import { formatDateTime } from "@/utils/date";

const props = withDefaults(defineProps<{
  type: EventType;
  title?: string | null;
  description?: string | null;
  priority?: Priority;
  status?: EventStatus;
  time?: string | null;
  durationMin?: number | null;
  hardDdl?: boolean;
  plans?: DdlPlan[];
  location?: string | null;
  teacher?: string | null;
  schedule?: string | null;
}>(), {
  title: "",
  description: "",
  priority: "mid",
  status: "todo",
  time: "",
  durationMin: null,
  hardDdl: false,
  plans: () => [],
  location: "",
  teacher: "",
  schedule: "",
});

const { t, locale } = useI18n();
const timeText = computed(() => props.time
  ? formatDateTime(props.time, locale.value === "en-US" ? "en-US" : "zh-CN")
  : t("preview.notSet"));
const activePlans = computed(() => props.plans.filter((plan) => plan.enabled !== false));
</script>

<template>
  <article class="event-detail-preview" :class="`event-detail-preview--${type}`">
    <header class="idea-detail-header event-detail-header">
      <div>
        <span class="event-detail-kind">{{ t(`event.type.${type}`) }}</span>
        <h2>{{ title?.trim() || t("preview.enterTitle") }}</h2>
        <time class="idea-time">{{ timeText }}</time>
      </div>
      <span class="tag" :class="`tag--${status}`">{{ t(`event.status.${status}`) }}</span>
    </header>
    <section class="idea-detail-copy event-detail-copy">
      <p>{{ description?.trim() || t("preview.noDescription") }}</p>
    </section>
    <dl class="event-detail-meta">
      <div>
        <dt>{{ type === "ddl" ? t("event.form.deadline") : type === "remind" ? t("event.form.triggerTime") : type === "course" ? t("course.nextClass") : t("event.form.startTime") }}</dt>
        <dd>{{ timeText }}</dd>
      </div>
      <div v-if="durationMin"><dt>{{ t("event.form.duration") }}</dt><dd>{{ durationMin }} {{ t("common.minutes") }}</dd></div>
      <div v-if="schedule"><dt>{{ t("preview.schedule") }}</dt><dd>{{ schedule }}</dd></div>
      <div v-if="location"><dt>{{ t("course.location") }}</dt><dd>{{ location }}</dd></div>
      <div v-if="teacher"><dt>{{ t("course.teacher") }}</dt><dd>{{ teacher }}</dd></div>
    </dl>
    <div class="event-detail-tags">
      <span class="tag" :class="`tag--prio-${priority}`">{{ t(`event.priority.${priority}`) }}</span>
      <span v-if="hardDdl" class="tag tag--hard">{{ t("event.form.hardDdl") }}</span>
    </div>
    <div v-if="type === 'ddl'" class="event-detail-plans">
      <strong>{{ t("event.form.plans") }}</strong>
      <div v-if="activePlans.length" class="event-detail-plan-list">
        <div v-for="(plan, index) in activePlans" :key="plan.planEvtId ?? index">
          <span>{{ plan.title || t(`preview.planRole.${plan.planRole}`) }}</span>
          <small>{{ formatDateTime(plan.stTime, locale === 'en-US' ? 'en-US' : 'zh-CN') }} · {{ plan.durationMin }} {{ t("common.minutes") }}</small>
        </div>
      </div>
      <span v-else class="muted-text">{{ t("preview.noLinkedPlans") }}</span>
    </div>
  </article>
</template>

<style scoped>
.event-detail-preview { --event-accent: #2563eb; min-width: 0; }
.event-detail-preview--remind { --event-accent: #9333ea; }
.event-detail-preview--ddl { --event-accent: #ea580c; }
.event-detail-preview--course { --event-accent: #0891b2; }
.event-detail-header { border-top: 4px solid var(--event-accent); padding-top: 18px; }
.event-detail-kind { display: block; margin-bottom: 5px; color: var(--event-accent); font-size: 12px; font-weight: 750; }
.event-detail-copy { padding-bottom: 16px; }
.event-detail-copy p { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.event-detail-meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; overflow: hidden; border: 1px solid var(--border-color); border-radius: 8px; background: var(--border-color); }
.event-detail-meta div { min-width: 0; padding: 12px; background: #fff; }
.event-detail-meta dt { color: var(--color-text-muted); font-size: 11px; }
.event-detail-meta dd { margin: 5px 0 0; overflow-wrap: anywhere; color: var(--color-text); font-weight: 700; }
.event-detail-tags { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 14px; }
.event-detail-plans { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border-color); }
.event-detail-plans > strong { font-size: 13px; }
.event-detail-plan-list { display: grid; gap: 8px; margin-top: 10px; }
.event-detail-plan-list > div { display: flex; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border-color); }
.event-detail-plan-list small { color: var(--color-text-muted); font-size: 11px; }
@media (max-width: 640px) {
  .event-detail-meta { grid-template-columns: 1fr; }
  .event-detail-plan-list > div { align-items: flex-start; flex-direction: column; }
}
</style>
