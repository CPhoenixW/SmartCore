<script setup lang="ts">
import { useI18n } from "vue-i18n";

defineProps<{ legacyPath: string }>();
const { t } = useI18n();
</script>

<template>
  <article class="detail-card migration-card">
    <span class="status-pill">Phase 1</span>
    <h1>{{ t("migration.title") }}</h1>
    <p>{{ t("migration.description") }}</p>
    <a class="primary-link" :href="legacyPath">{{ t("migration.openLegacy") }}</a>
  </article>
</template>
