<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { authApi } from "@/api/auth";
import { useUserStore } from "@/stores/user";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const userStore = useUserStore();
const search = ref(String(route.query.q ?? ""));
const mobileOpen = ref(false);
const loggingOut = ref(false);
const nav = [
  ["overview", "overview", "⌂"], ["add", "add", "+"], ["update", "update", "✎"], ["course", "course", "□"],
  ["device", "device", "◉"], ["ideas", "ideas", "◇"], ["logs", "logs", "≡"], ["settings", "settings", "⚙"],
] as const;
const initials = computed(() => userStore.user.displayName?.slice(0, 2).toUpperCase() || "SC");
const logoutLabel = computed(() => userStore.user.language === "en" ? "Log out" : "退出登录");
watch(() => route.query.q, (value) => { search.value = String(value ?? ""); });
onMounted(() => { if (!userStore.loaded) void userStore.load(); });
function submitSearch() { void router.push({ name: "update", query: { q: search.value || undefined } }); }
async function logout() {
  loggingOut.value = true;
  try { await authApi.logout(); } finally { window.location.href = "/work/login"; }
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar" :class="{ 'sidebar--open': mobileOpen }">
      <RouterLink class="brand" :to="{ name: 'overview' }" @click="mobileOpen = false"><span class="brand-mark">SC</span><span><strong>{{ t('app.name') }}</strong><small>{{ t('app.subtitle') }}</small></span></RouterLink>
      <nav class="nav-list" :aria-label="t('app.navigation')"><RouterLink v-for="item in nav" :key="item[0]" class="nav-link" :to="{ name: item[1] }" @click="mobileOpen = false"><span>{{ item[2] }}</span>{{ t(`nav.${item[0]}`) }}</RouterLink></nav>
      <button class="sidebar-logout" type="button" :disabled="loggingOut" @click="logout">{{ logoutLabel }}</button>
    </aside>
    <div v-if="mobileOpen" class="sidebar-backdrop" @click="mobileOpen = false" />
    <section class="workspace">
      <header class="topbar"><button class="mobile-menu" type="button" :aria-label="t('app.menu')" @click="mobileOpen = true">☰</button><form class="global-search" @submit.prevent="submitSearch"><span>⌕</span><input v-model="search" :placeholder="t('common.search')" /></form><div class="topbar-user"><span class="api-pill" :class="{ 'api-pill--loading': !userStore.loaded }">{{ userStore.loaded ? t('app.apiReady') : t('common.loading') }}</span><RouterLink class="avatar" :to="{ name: 'settings' }"><img v-if="userStore.user.avatarUrl" :src="userStore.user.avatarUrl" :alt="t('settings.avatarPreview')" /><span v-else>{{ initials }}</span></RouterLink></div></header>
      <main class="page"><RouterView /></main>
    </section>
  </div>
</template>

<style scoped>
.sidebar-logout{position:absolute;left:16px;right:16px;bottom:20px;min-height:40px;border:1px solid #334155;border-radius:10px;background:#111827;color:#cbd5e1;font-weight:700}.sidebar-logout:hover{background:#1e293b;color:#fff}.sidebar-logout:disabled{opacity:.55}
</style>
