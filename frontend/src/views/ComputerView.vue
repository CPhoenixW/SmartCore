<script setup lang="ts">
import { useI18n } from "vue-i18n";
import ComputerUsagePanel from "@/components/device/ComputerUsagePanel.vue";

const { t } = useI18n();
</script>

<template>
  <section class="device-section-heading">
    <div><h2>{{ t("computer.title") }}</h2><p>{{ t("computer.subtitle") }}</p></div>
  </section>
  <ComputerUsagePanel />
</template>
