<script setup lang="ts">
import { computed } from "vue";
import { Pencil, X } from "@lucide/vue";

const props = withDefaults(defineProps<{
  label: string;
  action?: "edit" | "close";
}>(), {
  action: "edit",
});

defineEmits<{ click: [event: MouseEvent] }>();
const icon = computed(() => props.action === "close" ? X : Pencil);
</script>

<template>
  <button class="preview-action-button" type="button" :title="label" :aria-label="label" @click="$emit('click', $event)">
    <component :is="icon" :size="14" :stroke-width="2" aria-hidden="true" />
  </button>
</template>

<style scoped>
.preview-action-button { display: grid; width: 26px; height: 26px; padding: 0; place-items: center; border: 1px solid #dbe2ea; border-radius: 6px; background: #f8fafc; color: #475569; transition: background .15s, border-color .15s, box-shadow .15s, color .15s; }
.preview-action-button:hover { border-color: #cbd5e1; background: #fff; color: #0f172a; box-shadow: 0 3px 10px rgb(15 23 42 / 8%); }
.preview-action-button:focus-visible { outline: 3px solid rgb(59 130 246 / 18%); outline-offset: 2px; }
</style>
