<script setup lang="ts">
defineProps<{ title: string; subtitle?: string; compact?: boolean }>();
</script>

<template>
  <header class="page-heading" :class="{ 'page-heading--compact': compact }">
    <div class="page-heading__copy">
      <component :is="compact ? 'h2' : 'h1'">{{ title }}</component>
      <p v-if="subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.actions" class="page-heading__actions"><slot name="actions" /></div>
  </header>
</template>
