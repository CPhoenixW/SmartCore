<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import StatusTag from "@/components/base/StatusTag.vue";
import type { SmartCoreEvent } from "@/types/event";
import { formatDateTime, getEventPrimaryTime } from "@/utils/date";
import { isOverdue } from "@/utils/event";

const props = defineProps<{ event: SmartCoreEvent; selected?: boolean }>();
defineEmits<{ select: [event: SmartCoreEvent]; edit: [event: SmartCoreEvent] }>();
const { t, locale } = useI18n();
const time = computed(() => formatDateTime(getEventPrimaryTime(props.event), locale.value === "en-US" ? "en-US" : "zh-CN"));
const overdue = computed(() => isOverdue(props.event));
</script>

<template>
  <button class="idea-card event-card" :class="[`event-card--${event.stat}`, `event-card--type-${event.evtType}`, { 'event-card--selected': selected, 'event-card--overdue': overdue }]" type="button" @click="$emit('select', event)" @dblclick="$emit('edit', event)">
    <strong>{{ event.title }}</strong>
    <p>{{ event.desc || t("preview.noDescription") }}</p>
    <footer>
      <span class="event-card__tags">
        <StatusTag :type="event.evtType" :text="t(`event.type.${event.evtType}`)" />
        <StatusTag :status="event.stat" :text="t(`event.status.${event.stat}`)" />
        <StatusTag :priority="event.prio" :text="t(`event.priority.${event.prio}`)" />
        <span v-if="overdue" class="tag tag--cancelled">{{ locale === 'en-US' ? 'Overdue' : '已逾期' }}</span>
        <span v-if="event.evtType === 'plan' && event.generatedBy" class="tag tag--done">{{ event.generatedBy === 'course' ? (locale === 'en-US' ? 'Course plan' : '课程生成') : 'DDL plan' }}</span>
      </span>
      <time :datetime="getEventPrimaryTime(event)">{{ time }}</time>
    </footer>
  </button>
</template>
