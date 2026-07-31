<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  BookOpen,
  Calendar,
  CalendarPlus,
  House,
  Lightbulb,
  List,
  Menu,
  Monitor,
  Pencil,
  Search,
  Settings,
} from "@lucide/vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { authApi } from "@/api/auth";
import smartcoreMarkBlue from "@/assets/smartcore-mark-blue.png";
import { useUserStore } from "@/stores/user";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const userStore = useUserStore();
const search = ref(String(route.query.q ?? ""));
const mobileOpen = ref(false);
const loggingOut = ref(false);
const nav = [
  { key: "overview", name: "overview", icon: House },
  { key: "dailySummary", name: "dailySummary", icon: Calendar },
  { key: "add", name: "add", icon: CalendarPlus },
  { key: "update", name: "update", icon: Pencil },
  { key: "course", name: "course", icon: BookOpen },
  { key: "device", name: "device", icon: Monitor },
  { key: "ideas", name: "ideas", icon: Lightbulb },
  { key: "logs", name: "logs", icon: List },
  { key: "settings", name: "settings", icon: Settings },
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
      <RouterLink class="brand" :to="{ name: 'overview' }" @click="mobileOpen = false"><span class="brand-mark"><img :src="smartcoreMarkBlue" alt="" aria-hidden="true" /></span><span><strong>{{ t('app.name') }}</strong><small>{{ t('app.subtitle') }}</small></span></RouterLink>
      <nav class="nav-list" :aria-label="t('app.navigation')"><RouterLink v-for="item in nav" :key="item.key" class="nav-link" :class="{ 'nav-link--active': item.name === 'device' && route.path.startsWith('/device') }" :to="{ name: item.name }" @click="mobileOpen = false"><component :is="item.icon" class="nav-link__icon" :size="17" :stroke-width="1.8" aria-hidden="true" />{{ t(`nav.${item.key}`) }}</RouterLink></nav>
      <button class="sidebar-logout" type="button" :disabled="loggingOut" @click="logout">{{ logoutLabel }}</button>
    </aside>
    <div v-if="mobileOpen" class="sidebar-backdrop" @click="mobileOpen = false" />
    <section class="workspace">
      <header class="topbar"><button class="mobile-menu" type="button" :aria-label="t('app.menu')" @click="mobileOpen = true"><Menu :size="20" aria-hidden="true" /></button><form class="global-search" @submit.prevent="submitSearch"><Search :size="16" aria-hidden="true" /><input v-model="search" :placeholder="t('common.search')" /></form><div class="topbar-user"><span class="api-pill" :class="{ 'api-pill--loading': !userStore.loaded }">{{ userStore.loaded ? t('app.apiReady') : t('common.loading') }}</span><RouterLink class="avatar" :to="{ name: 'settings' }"><img v-if="userStore.user.avatarUrl" :src="userStore.user.avatarUrl" :alt="t('settings.avatarPreview')" /><span v-else>{{ initials }}</span></RouterLink></div></header>
      <main class="page"><RouterView /></main>
    </section>
  </div>
</template>

<style scoped>
.brand-mark{overflow:hidden;background:#000}.brand-mark img{width:100%;height:100%;object-fit:cover}.nav-link--active{background:#1e293b;color:#fff}.nav-link__icon{flex:0 0 18px}.sidebar-logout{position:absolute;left:16px;right:16px;bottom:20px;min-height:40px;border:1px solid #334155;border-radius:10px;background:#111827;color:#cbd5e1;font-weight:700}.sidebar-logout:hover{background:#1e293b;color:#fff}.sidebar-logout:disabled{opacity:.55}
</style>
