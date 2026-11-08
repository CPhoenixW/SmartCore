<script setup lang="ts">
import { ArrowLeft, Bell } from "@lucide/vue";
import { useI18n } from "vue-i18n";
import NotificationInbox from "@/components/overview/NotificationInbox.vue";

const { t } = useI18n();
</script>

<template>
  <div class="notifications-page">
    <div class="page-heading">
      <div class="page-heading__copy">
        <Bell :size="22" aria-hidden="true" />
        <div>
          <h1>{{ t("notifications.pageTitle") }}</h1>
          <p>{{ t("notifications.pageHint") }}</p>
        </div>
      </div>
      <RouterLink class="button button--ghost" :to="{ name: 'overview' }">
        <ArrowLeft :size="15" aria-hidden="true" />
        {{ t("notifications.backToOverview") }}
      </RouterLink>
    </div>
    <NotificationInbox :limit="50" />
  </div>
</template>

<style scoped>
.notifications-page { display: grid; gap: 18px; }
.page-heading__copy { display: flex; align-items: center; gap: 10px; }
.page-heading__copy > svg { flex: 0 0 auto; color: var(--color-primary); }
.page-heading__copy > div { display: grid; gap: 4px; }
.page-heading__copy h1 { margin: 0; }
.page-heading__copy p { margin: 0; }
.page-heading .button { display: inline-flex; align-items: center; gap: 7px; }
</style>
