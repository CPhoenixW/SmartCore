<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  Bell,
  BookOpen,
  Bot,
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
import { useViewport } from "@/composables/useViewport";
import { bindStagedWheelScroll } from "@/utils/scroll";
import { notificationsApi, vapidKeyBytes } from "@/api/notifications";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const userStore = useUserStore();
const { isMobile } = useViewport();
const search = ref(String(route.query.q ?? ""));
const mobileOpen = ref(false);
const loggingOut = ref(false);
const pageRoot = ref<HTMLElement | null>(null);
const secondaryOpen = ref(false);
const pushSupported = ref(false);
const pushEnabled = ref(false);
const pushBusy = ref(false);
const pushMessage = ref("");
let stopStagedWheelScroll: (() => void) | undefined;

/** Desktop keeps the full workbench nav; phone keeps the PWA four-tab shell. */
const desktopPrimaryNav = [
  { key: "overview", name: "overview", icon: House },
  { key: "assistant", name: "assistant", icon: Bot },
  { key: "course", name: "course", icon: BookOpen },
  { key: "add", name: "add", icon: CalendarPlus },
] as const;
const desktopSecondaryNav = [
  { key: "schedule", name: "schedule", icon: Calendar },
  { key: "dailySummary", name: "dailySummary", icon: Calendar },
  { key: "update", name: "update", icon: Pencil },
  { key: "device", name: "device", icon: Monitor },
  { key: "ideas", name: "ideas", icon: Lightbulb },
  { key: "logs", name: "logs", icon: List },
  { key: "settings", name: "settings", icon: Settings },
] as const;
const mobilePrimaryNav = [
  { key: "overview", name: "overview", icon: House },
  { key: "assistant", name: "assistant", icon: Bot },
  { key: "schedule", name: "schedule", icon: Calendar },
  { key: "settings", name: "settings", icon: Settings },
] as const;

const primaryNav = computed(() => (isMobile.value ? mobilePrimaryNav : desktopPrimaryNav));
const secondaryNav = computed(() => (isMobile.value ? [] : desktopSecondaryNav));
const initials = computed(() => userStore.user.displayName?.slice(0, 2).toUpperCase() || "SC");
const logoutLabel = computed(() => (userStore.user.language === "en" ? "Log out" : "退出登录"));
const knownRouteNames = computed(() => {
  const names = new Set<string>([
    ...desktopPrimaryNav.map((item) => item.name),
    ...desktopSecondaryNav.map((item) => item.name),
    ...mobilePrimaryNav.map((item) => item.name),
  ]);
  return names;
});
const routeTitleKey = computed(() => {
  const name = String(route.name || "overview");
  if (name.startsWith("device")) return "device";
  return knownRouteNames.value.has(name) ? name : "overview";
});
const pageTitle = computed(() => t(`nav.${routeTitleKey.value}`));

watch(
  () => route.query.q,
  (value) => {
    search.value = String(value ?? "");
  },
);
watch(isMobile, (mobile) => {
  if (mobile) secondaryOpen.value = false;
});

onMounted(() => {
  if (!userStore.loaded) void userStore.load();
  if (pageRoot.value) stopStagedWheelScroll = bindStagedWheelScroll(pageRoot.value);
  void loadPushState();
});
onBeforeUnmount(() => stopStagedWheelScroll?.());

function submitSearch() {
  void router.push({ name: "update", query: { q: search.value || undefined } });
}

async function logout() {
  loggingOut.value = true;
  try {
    await authApi.logout();
  } finally {
    window.location.href = "/work/login";
  }
}

async function loadPushState(): Promise<void> {
  pushSupported.value =
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "Notification" in window &&
    "PushManager" in window;
  if (!pushSupported.value) return;
  try {
    const registration = await navigator.serviceWorker.ready;
    pushEnabled.value = Boolean(await registration.pushManager.getSubscription());
  } catch {
    pushEnabled.value = false;
  }
}

async function enablePush(): Promise<void> {
  if (!pushSupported.value || pushBusy.value) return;
  pushBusy.value = true;
  pushMessage.value = "";
  try {
    const permission =
      Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
    if (permission !== "granted") {
      pushMessage.value = t("app.notificationsDenied");
      return;
    }
    const config = await notificationsApi.publicKey();
    if (!config.enabled || !config.publicKey) {
      pushMessage.value = t("app.notificationsUnavailable");
      return;
    }
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: vapidKeyBytes(config.publicKey),
    });
    const json = subscription.toJSON();
    if (!json.endpoint || !json.keys?.p256dh || !json.keys.auth) throw new Error("invalid push subscription");
    await notificationsApi.subscribe({
      endpoint: json.endpoint,
      keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
    });
    pushEnabled.value = true;
    pushMessage.value = t("app.notificationsEnabled");
  } catch {
    pushMessage.value = t("app.notificationsUnavailable");
  } finally {
    pushBusy.value = false;
  }
}
</script>

<template>
  <div class="app-shell" :class="{ 'app-shell--mobile': isMobile, 'app-shell--desktop': !isMobile }">
    <aside class="sidebar" :class="{ 'sidebar--open': mobileOpen }">
      <RouterLink class="brand" :to="{ name: 'overview' }" @click="mobileOpen = false">
        <span class="brand-mark"><img :src="smartcoreMarkBlue" alt="" aria-hidden="true" /></span>
        <span>
          <strong>{{ t('app.name') }}</strong>
          <small>{{ t('app.subtitle') }}</small>
        </span>
      </RouterLink>
      <nav class="nav-list" :aria-label="t('app.navigation')">
        <RouterLink
          v-for="item in primaryNav"
          :key="item.key"
          class="nav-link"
          :to="{ name: item.name }"
          @click="mobileOpen = false"
        >
          <component :is="item.icon" class="nav-link__icon" :size="17" :stroke-width="1.8" aria-hidden="true" />
          {{ t(`nav.${item.key}`) }}
        </RouterLink>
      </nav>
      <template v-if="!isMobile">
        <button
          class="nav-more-toggle"
          type="button"
          :aria-expanded="secondaryOpen"
          @click="secondaryOpen = !secondaryOpen"
        >
          <List class="nav-link__icon" :size="17" :stroke-width="1.8" aria-hidden="true" />
          {{ t('app.more') }}
          <span aria-hidden="true">{{ secondaryOpen ? '−' : '+' }}</span>
        </button>
        <nav v-show="secondaryOpen" class="nav-list nav-list--secondary" :aria-label="t('app.more')">
          <RouterLink
            v-for="item in secondaryNav"
            :key="item.key"
            class="nav-link"
            :class="{ 'nav-link--active': item.name === 'device' && route.path.startsWith('/device') }"
            :to="{ name: item.name }"
            @click="mobileOpen = false"
          >
            <component :is="item.icon" class="nav-link__icon" :size="17" :stroke-width="1.8" aria-hidden="true" />
            {{ t(`nav.${item.key}`) }}
          </RouterLink>
        </nav>
      </template>
      <button class="sidebar-logout" type="button" :disabled="loggingOut" @click="logout">{{ logoutLabel }}</button>
    </aside>
    <div v-if="mobileOpen" class="sidebar-backdrop" @click="mobileOpen = false" />
    <section class="workspace">
      <header class="topbar">
        <button class="mobile-menu" type="button" :aria-label="t('app.menu')" @click="mobileOpen = true">
          <Menu :size="20" aria-hidden="true" />
        </button>
        <strong v-if="isMobile" class="topbar-title">{{ pageTitle }}</strong>
        <form v-else class="global-search" @submit.prevent="submitSearch">
          <Search :size="16" aria-hidden="true" />
          <input v-model="search" :placeholder="t('common.search')" />
        </form>
        <div class="topbar-user">
          <button
            v-if="pushSupported"
            class="notification-button"
            type="button"
            :title="pushMessage || (pushEnabled ? t('app.notificationsEnabled') : t('app.enableNotifications'))"
            :aria-label="pushMessage || (pushEnabled ? t('app.notificationsEnabled') : t('app.enableNotifications'))"
            :disabled="pushBusy || pushEnabled"
            @click="enablePush"
          >
            <Bell :size="18" aria-hidden="true" />
            <span v-if="pushEnabled" class="notification-button__dot" />
          </button>
          <span v-if="!isMobile" class="api-pill" :class="{ 'api-pill--loading': !userStore.loaded }">
            {{ userStore.loaded ? t('app.apiReady') : t('common.loading') }}
          </span>
          <RouterLink class="avatar" :to="{ name: 'settings' }">
            <img v-if="userStore.user.avatarUrl" :src="userStore.user.avatarUrl" :alt="t('settings.avatarPreview')" />
            <span v-else>{{ initials }}</span>
          </RouterLink>
        </div>
      </header>
      <main ref="pageRoot" class="page"><RouterView /></main>
    </section>
  </div>
</template>

<style scoped>
.brand-mark {
  overflow: hidden;
  background: #000;
}
.brand-mark img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.nav-link--active {
  background: #1e293b;
  color: #fff;
}
.nav-link__icon {
  flex: 0 0 18px;
}
.nav-more-toggle {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  margin-top: 16px;
  padding: 11px 12px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: #94a3b8;
  text-align: left;
  font: inherit;
}
.nav-more-toggle:hover {
  background: #1e293b;
  color: #fff;
}
.nav-more-toggle > span {
  margin-left: auto;
}
.nav-list--secondary {
  margin-top: 4px;
}
.topbar-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 17px;
}
.notification-button {
  position: relative;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: #fff;
  color: #475569;
}
.notification-button:hover {
  border-color: #93c5fd;
  color: #1d4ed8;
}
.notification-button:disabled {
  cursor: default;
  opacity: 0.7;
}
.notification-button__dot {
  position: absolute;
  top: 7px;
  right: 7px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #16a34a;
}
.sidebar-logout {
  position: absolute;
  left: 16px;
  right: 16px;
  bottom: 20px;
  min-height: 40px;
  border: 1px solid #334155;
  border-radius: 10px;
  background: #111827;
  color: #cbd5e1;
  font-weight: 700;
}
.sidebar-logout:hover {
  background: #1e293b;
  color: #fff;
}
.sidebar-logout:disabled {
  opacity: 0.55;
}
@media (max-width: 760px) {
  .nav-more-toggle {
    margin-top: 12px;
  }
  .page {
    padding-bottom: 24px;
  }
}
</style>
