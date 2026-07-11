<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { useUserStore } from "@/stores/user";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const userStore = useUserStore();
const search = ref(String(route.query.q ?? ""));
const mobileOpen = ref(false);
const nav = [
  ["overview", "overview", "⌂"], ["add", "add", "+"], ["update", "update", "✎"], ["course", "course", "□"],
  ["device", "device", "◉"], ["ideas", "ideas", "◇"], ["logs", "logs", "≡"], ["settings", "settings", "⚙"],
] as const;
const initials = computed(() => userStore.user.displayName?.slice(0, 2).toUpperCase() || "SC");
watch(() => route.query.q, (value) => { search.value = String(value ?? ""); });
onMounted(() => { if (!userStore.loaded) void userStore.load(); });
function submitSearch() { void router.push({ name: "update", query: { q: search.value || undefined } }); }
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar" :class="{ 'sidebar--open': mobileOpen }">
      <RouterLink class="brand" :to="{ name: 'overview' }" @click="mobileOpen = false"><span class="brand-mark">SC</span><span><strong>{{ t('app.name') }}</strong><small>{{ t('app.subtitle') }}</small></span></RouterLink>
      <nav class="nav-list" aria-label="workbench navigation"><RouterLink v-for="item in nav" :key="item[0]" class="nav-link" :to="{ name: item[1] }" @click="mobileOpen = false"><span>{{ item[2] }}</span>{{ t(`nav.${item[0]}`) }}</RouterLink></nav>
      <a class="legacy-link" href="/work-legacy">Legacy UI</a>
    </aside>
    <div v-if="mobileOpen" class="sidebar-backdrop" @click="mobileOpen = false" />
    <section class="workspace">
      <header class="topbar"><button class="mobile-menu" type="button" aria-label="menu" @click="mobileOpen = true">☰</button><form class="global-search" @submit.prevent="submitSearch"><span>⌕</span><input v-model="search" :placeholder="t('common.search')" /></form><div class="topbar-user"><span class="api-pill" :class="{ 'api-pill--loading': !userStore.loaded }">{{ userStore.loaded ? t('app.apiReady') : t('common.loading') }}</span><RouterLink class="avatar" :to="{ name: 'settings' }"><img v-if="userStore.user.avatarUrl" :src="userStore.user.avatarUrl" alt="" /><span v-else>{{ initials }}</span></RouterLink></div></header>
      <main class="page"><RouterView /></main>
    </section>
  </div>
</template>
