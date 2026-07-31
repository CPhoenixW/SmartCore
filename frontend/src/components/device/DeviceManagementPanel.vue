<script setup lang="ts">
withDefaults(defineProps<{ title: string; summary: string; icon: string; initiallyOpen?: boolean }>(), {
  initiallyOpen: false,
});
</script>

<template>
  <details class="device-management-panel" :open="initiallyOpen">
    <summary>
      <span class="device-management-panel__copy">
        <i>{{ icon }}</i>
        <span><strong>{{ title }}</strong><small>{{ summary }}</small></span>
      </span>
      <span class="device-management-panel__chevron">⌄</span>
    </summary>
    <div class="device-management-panel__body"><slot /></div>
  </details>
</template>
