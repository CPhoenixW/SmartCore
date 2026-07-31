<script setup lang="ts">
import { Inbox } from "@lucide/vue";

defineProps<{ text?: string }>();
</script>

<template>
  <div class="empty-state">
    <Inbox class="empty-state__icon" :size="24" :stroke-width="1.6" aria-hidden="true" />
    <p>{{ text ?? $t("common.empty") }}</p>
  </div>
</template>

<style scoped>
.empty-state__icon { color: #94a3b8; }
</style>
