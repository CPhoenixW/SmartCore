<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import StatusTag from "@/components/base/StatusTag.vue";
import type { SmartCoreEvent } from "@/types/event";
import { formatDateTime, getEventPrimaryTime } from "@/utils/date";

const props = defineProps<{ event: SmartCoreEvent; selected?: boolean }>();
defineEmits<{ select: [event: SmartCoreEvent] }>();
const { t, locale } = useI18n();
const time = computed(() => formatDateTime(getEventPrimaryTime(props.event), locale.value === "en-US" ? "en-US" : "zh-CN"));
</script>
<template>
  <button class="event-card" :class="[`event-card--${event.stat}`, { 'event-card--selected': selected }]" type="button" @click="$emit('select', event)">
    <div class="event-card__top"><strong>{{ event.title }}</strong><time>{{ time }}</time></div>
    <p v-if="event.desc">{{ event.desc }}</p>
    <div class="event-card__tags">
      <StatusTag :type="event.evtType" :text="t(`event.type.${event.evtType}`)" />
      <StatusTag :status="event.stat" :text="t(`event.status.${event.stat}`)" />
      <StatusTag :priority="event.prio" :text="t(`event.priority.${event.prio}`)" />
    </div>
  </button>
</template>
