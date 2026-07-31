<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import DetailPreview from "@/components/base/DetailPreview.vue";
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
  <DetailPreview
    class="event-detail-preview"
    :title="title?.trim() || t('preview.enterTitle')"
    :description="description"
    :empty-description="t('preview.noDescription')"
    :time="timeText"
  >
    <template #badge>
      <span class="tag" :class="`tag--${type}`">{{ t(`event.type.${type}`) }}</span>
      <span v-if="status !== 'done'" class="tag" :class="`tag--${status}`">{{ t(`event.status.${status}`) }}</span>
    </template>
    <section v-if="durationMin || schedule || location || teacher || hardDdl" class="idea-attachment-section event-detail-section">
      <h3>{{ t("preview.details") }}</h3>
      <dl class="event-detail-meta">
        <div v-if="durationMin"><dt>{{ t("event.form.duration") }}</dt><dd>{{ durationMin }} {{ t("common.minutes") }}</dd></div>
        <div v-if="schedule"><dt>{{ t("preview.schedule") }}</dt><dd>{{ schedule }}</dd></div>
        <div v-if="location"><dt>{{ t("course.location") }}</dt><dd>{{ location }}</dd></div>
        <div v-if="teacher"><dt>{{ t("course.teacher") }}</dt><dd>{{ teacher }}</dd></div>
      </dl>
      <div class="event-detail-tags">
        <span class="tag" :class="`tag--prio-${priority}`">{{ t(`event.priority.${priority}`) }}</span>
        <span v-if="hardDdl" class="tag tag--hard">{{ t("event.form.hardDdl") }}</span>
      </div>
    </section>
    <div v-else class="event-detail-tags">
      <span class="tag" :class="`tag--prio-${priority}`">{{ t(`event.priority.${priority}`) }}</span>
    </div>
    <section v-if="type === 'ddl'" class="idea-attachment-section event-detail-plans">
      <h3>{{ t("event.form.plans") }}</h3>
      <div v-if="activePlans.length" class="event-detail-plan-list">
        <div v-for="(plan, index) in activePlans" :key="plan.planEvtId ?? index">
          <span>{{ plan.title || t(`preview.planRole.${plan.planRole}`) }}</span>
          <small>{{ formatDateTime(plan.stTime, locale === 'en-US' ? 'en-US' : 'zh-CN') }} · {{ plan.durationMin }} {{ t("common.minutes") }}</small>
        </div>
      </div>
      <span v-else class="muted-text">{{ t("preview.noLinkedPlans") }}</span>
    </section>
  </DetailPreview>
</template>

<style scoped>
.event-detail-preview { min-width: 0; }
.event-detail-meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 24px; margin-top: 12px; }
.event-detail-meta div { min-width: 0; padding-bottom: 10px; border-bottom: 1px solid #eef2f7; }
.event-detail-meta dt { color: var(--color-text-muted); font-size: 11px; }
.event-detail-meta dd { margin: 5px 0 0; overflow-wrap: anywhere; color: var(--color-text); font-weight: 700; }
.event-detail-tags { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 14px; }
.event-detail-plan-list { display: grid; gap: 8px; margin-top: 10px; }
.event-detail-plan-list > div { display: flex; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border-color); }
.event-detail-plan-list small { color: var(--color-text-muted); font-size: 11px; }
@media (max-width: 640px) {
  .event-detail-meta { grid-template-columns: 1fr; }
  .event-detail-plan-list > div { align-items: flex-start; flex-direction: column; }
}
</style>
