<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const { locale, t } = useI18n();

const items = [
  ["overview", "/"],
  ["add", "/add"],
  ["update", "/update"],
  ["course", "/course"],
  ["device", "/device"],
  ["ideas", "/ideas"],
  ["logs", "/logs"],
  ["settings", "/settings"],
] as const;

const nextLocale = computed(() => (locale.value === "zh-CN" ? "en-US" : "zh-CN"));

function toggleLocale() {
  locale.value = nextLocale.value;
  window.localStorage.setItem("smartcore.locale", locale.value);
}
</script>

<template>
  <div class="work-layout">
    <aside class="sidebar">
      <RouterLink class="brand" to="/">
        <span class="brand-mark">SC</span>
        <span><strong>{{ t("app.name") }}</strong><small>{{ t("app.subtitle") }}</small></span>
      </RouterLink>
      <nav>
        <RouterLink v-for="([key, path]) in items" :key="key" :to="path">
          {{ t(`nav.${key}`) }}
        </RouterLink>
      </nav>
      <a class="legacy-link" href="/work">{{ t("app.legacy") }}</a>
    </aside>
    <section class="content-shell">
      <header class="topbar">
        <span class="status-pill">Vue 3 + TypeScript</span>
        <button class="language-button" type="button" @click="toggleLocale">
          {{ nextLocale === "en-US" ? "EN" : "中文" }}
        </button>
      </header>
      <main class="page-main">
        <RouterView />
      </main>
    </section>
  </div>
</template>
