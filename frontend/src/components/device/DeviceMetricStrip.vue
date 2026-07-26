<script setup lang="ts">
export interface DeviceMetric {
  label: string;
  value: string;
  note?: string;
  tone?: "primary" | "success" | "warning" | "neutral";
}

defineProps<{ items: DeviceMetric[]; label?: string }>();
</script>

<template>
  <section class="device-metric-strip" :aria-label="label">
    <article v-for="item in items" :key="item.label" class="device-metric" :class="`device-metric--${item.tone ?? 'primary'}`">
      <span>{{ item.label }}</span>
      <strong>{{ item.value }}</strong>
      <small v-if="item.note">{{ item.note }}</small>
    </article>
  </section>
</template>
