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
const icon = computed(() => ({ plan: "✓", remind: "◷", ddl: "!", course: "▦" })[props.type]);
const timeText = computed(() => props.time
  ? formatDateTime(props.time, locale.value === "en-US" ? "en-US" : "zh-CN")
  : t("preview.notSet"));
const activePlans = computed(() => props.plans.filter((plan) => plan.enabled !== false));
</script>

<template>
  <article class="visual-preview" :class="`visual-preview--${type}`">
    <header class="visual-preview__header">
      <span class="visual-preview__icon">{{ icon }}</span>
      <div>
        <small>{{ t(`event.type.${type}`) }}</small>
        <h3>{{ title?.trim() || t("preview.enterTitle") }}</h3>
      </div>
    </header>
    <p class="visual-preview__description">{{ description?.trim() || t("preview.noDescription") }}</p>
    <div class="visual-preview__timeline">
      <span class="visual-preview__dot" />
      <div>
        <small>{{ type === "ddl" ? t("event.form.deadline") : type === "remind" ? t("event.form.triggerTime") : type === "course" ? t("course.nextClass") : t("event.form.startTime") }}</small>
        <strong>{{ timeText }}</strong>
      </div>
    </div>
    <div v-if="schedule || location || teacher" class="visual-preview__course-meta">
      <span v-if="schedule">{{ schedule }}</span>
      <span v-if="location">⌖ {{ location }}</span>
      <span v-if="teacher">◎ {{ teacher }}</span>
    </div>
    <div class="visual-preview__tags">
      <span class="tag" :class="`tag--${type}`">{{ t(`event.type.${type}`) }}</span>
      <span class="tag" :class="`tag--prio-${priority}`">{{ t(`event.priority.${priority}`) }}</span>
      <span class="tag" :class="`tag--${status}`">{{ t(`event.status.${status}`) }}</span>
      <span v-if="durationMin" class="tag tag--duration">{{ durationMin }} {{ t("common.minutes") }}</span>
      <span v-if="hardDdl" class="tag tag--hard">{{ t("event.form.hardDdl") }}</span>
    </div>
    <div v-if="type === 'ddl'" class="visual-preview__plans">
      <strong>{{ t("event.form.plans") }}</strong>
      <div v-if="activePlans.length" class="visual-preview__plan-list">
        <div v-for="(plan, index) in activePlans" :key="plan.planEvtId ?? index">
          <span>{{ plan.title || t(`preview.planRole.${plan.planRole}`) }}</span>
          <small>{{ formatDateTime(plan.stTime, locale === 'en-US' ? 'en-US' : 'zh-CN') }} · {{ plan.durationMin }} {{ t("common.minutes") }}</small>
        </div>
      </div>
      <span v-else class="muted-text">{{ t("preview.noLinkedPlans") }}</span>
    </div>
  </article>
</template>
