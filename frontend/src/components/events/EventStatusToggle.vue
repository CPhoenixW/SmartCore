<script setup lang="ts">
import { computed } from "vue";
import type { EventStatus } from "@/types/event";

const props = defineProps<{
  status: EventStatus;
  busy?: boolean;
  markDoneLabel: string;
  markTodoLabel: string;
}>();
const emit = defineEmits<{ change: [status: "todo" | "done"] }>();
const checked = computed(() => props.status === "done");
const label = computed(() => checked.value ? props.markTodoLabel : props.markDoneLabel);

function change(event: Event) {
  emit("change", (event.target as HTMLInputElement).checked ? "done" : "todo");
}
</script>

<template>
  <label class="event-status-toggle" :title="label">
    <input
      :aria-label="label"
      :checked="checked"
      :disabled="busy"
      type="checkbox"
      @change="change"
    />
  </label>
</template>

<style scoped>
.event-status-toggle {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  cursor: pointer;
}
.event-status-toggle input {
  display: grid;
  place-items: center;
  width: 21px;
  height: 21px;
  margin: 0;
  appearance: none;
  border: 2px solid #94a3b8;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  transition: border-color .15s, background-color .15s;
}
.event-status-toggle input::after {
  color: #fff;
  content: "✓";
  font-size: 14px;
  font-weight: 800;
  line-height: 1;
  opacity: 0;
}
.event-status-toggle input:checked {
  border-color: var(--color-primary);
  background: var(--color-primary);
}
.event-status-toggle input:checked::after {
  opacity: 1;
}
.event-status-toggle input:disabled {
  cursor: wait;
  opacity: .55;
}
</style>
