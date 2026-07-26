<script setup lang="ts">
import { useI18n } from "vue-i18n";
import ComputerUsagePanel from "@/components/device/ComputerUsagePanel.vue";
import PageHeader from "@/components/base/PageHeader.vue";

const { t } = useI18n();
</script>

<template>
  <div class="device-data-page">
    <PageHeader compact :title="t('computer.title')" :subtitle="t('computer.subtitle')" />
    <ComputerUsagePanel />
  </div>
</template>
