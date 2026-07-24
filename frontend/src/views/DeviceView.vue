<script setup lang="ts">
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const sections = [
  { name: "deviceRaspberryPi", label: "device.sections.raspberryPi" },
  { name: "deviceComputer", label: "device.sections.computer" },
  { name: "deviceScreen", label: "device.sections.screen" },
  { name: "deviceFeishuBot", label: "device.sections.feishuBot" },
] as const;
</script>

<template>
  <section class="page-heading device-page-heading">
    <div><h1>{{ t("device.title") }}</h1><p>{{ t("device.subtitle") }}</p></div>
  </section>
  <nav class="device-section-nav" :aria-label="t('device.sectionNavigation')">
    <RouterLink v-for="section in sections" :key="section.name" :to="{ name: section.name }">
      {{ t(section.label) }}
    </RouterLink>
  </nav>
  <RouterView />
</template>
