<script setup lang="ts">
import { useI18n } from "vue-i18n";
import PageHeader from "@/components/base/PageHeader.vue";

const { t } = useI18n();

const sections = [
  { name: "deviceComputer", label: "device.sections.computer" },
  { name: "deviceRaspberryPi", label: "device.sections.raspberryPi" },
  { name: "deviceScreen", label: "device.sections.screen" },
] as const;
</script>

<template>
  <PageHeader class="device-page-heading" :title="t('device.title')" :subtitle="t('device.subtitle')" />
  <nav class="device-section-nav" :aria-label="t('device.sectionNavigation')">
    <RouterLink v-for="section in sections" :key="section.name" :to="{ name: section.name }">
      {{ t(section.label) }}
    </RouterLink>
  </nav>
  <RouterView />
</template>
