<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();
const apiReady = ref<boolean | null>(null);

onMounted(async () => {
  try {
    const response = await fetch("/healthz", { headers: { Accept: "application/json" } });
    apiReady.value = response.ok;
  } catch {
    apiReady.value = false;
  }
});
</script>

<template>
  <section class="page-head">
    <div>
      <h1>{{ t("overview.title") }}</h1>
      <p>{{ t("overview.description") }}</p>
    </div>
    <span class="status-pill" :class="{ danger: apiReady === false }">
      {{ apiReady === false ? t("app.apiOffline") : t("app.apiReady") }}
    </span>
  </section>

  <section class="card-grid">
    <article class="card">
      <span>{{ t("overview.foundation") }}</span>
      <strong>{{ t("overview.foundationValue") }}</strong>
    </article>
    <article class="card">
      <span>Legacy</span>
      <strong>{{ t("overview.legacyValue") }}</strong>
    </article>
    <article class="card">
      <span>{{ t("overview.deployment") }}</span>
      <strong>{{ t("overview.deploymentValue") }}</strong>
    </article>
  </section>

  <article class="detail-card">
    <h2>{{ t("overview.architecture") }}</h2>
    <pre>Browser → Vue SPA → /api/* → FastAPI → SQLite / Scheduler / Feishu / OpenClaw</pre>
  </article>
</template>
