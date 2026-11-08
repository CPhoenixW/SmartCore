<script setup lang="ts">
import { computed } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { CheckCircle2, CircleAlert, ExternalLink, RefreshCw } from "@lucide/vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import { notificationsApi, type NotificationRecord } from "@/api/notifications";

const props = withDefaults(defineProps<{ limit?: number }>(), { limit: 8 });
const { t, locale } = useI18n();
const router = useRouter();
const notificationQuery = useQuery({
  queryKey: computed(() => ["notifications", "inbox", props.limit]),
  queryFn: () => notificationsApi.list(props.limit),
  refetchInterval: 30_000,
});
const rows = computed(() => (notificationQuery.data.value ?? []).slice(0, props.limit));

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.replace("T", " ");
  return new Intl.DateTimeFormat(locale.value === "en-US" ? "en-US" : "zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function tone(row: NotificationRecord): "critical" | "failed" | "info" {
  if (row.stat !== "sent") return "failed";
  if (/ddl|截止|逾期|deadline|overdue|ends|结束/i.test(`${row.title} ${row.content}`)) return "critical";
  return "info";
}

function channelLabel(channel: string): string {
  if (channel === "browser") return t("notifications.channel.browser");
  if (channel === "screen") return t("notifications.channel.screen");
  return channel;
}

function statusLabel(row: NotificationRecord): string {
  const state = row.deliveryState || (row.stat === "sent" ? "accepted" : row.stat);
  if (state === "accepted") return t("notifications.status.accepted");
  if (state === "connected") return t("notifications.status.connected");
  if (state === "pending") return t("notifications.status.pending");
  if (state === "failed") return t("notifications.status.failed");
  return t("notifications.status.recorded");
}

function openNotification(row: NotificationRecord): void {
  if (row.evtId) {
    void router.push({ name: "update", query: { evtId: row.evtId } });
    return;
  }
  void router.push({ name: "assistant", query: { prompt: `${t("notifications.openPrompt")}：${row.title}` } });
}

function refresh(): void {
  void notificationQuery.refetch?.();
}
</script>

<template>
  <BaseCard class="notification-inbox" :title="t('notifications.inboxTitle')">
    <template #actions>
      <button class="icon-button" type="button" :aria-label="t('common.refresh')" :title="t('common.refresh')" @click="refresh">
        <RefreshCw :size="15" aria-hidden="true" />
      </button>
    </template>
    <p class="notification-inbox__hint">{{ t('notifications.inboxHint') }}</p>
    <div v-if="notificationQuery.isPending.value" class="empty-state notification-inbox__loading">{{ t('common.loading') }}</div>
    <div v-else-if="rows.length" class="notification-inbox__list">
      <button v-for="row in rows" :key="row.notifyId" class="notification-inbox__row" :class="`notification-inbox__row--${tone(row)}`" type="button" @click="openNotification(row)">
        <span class="notification-inbox__icon">
          <CircleAlert v-if="tone(row) === 'critical' || tone(row) === 'failed'" :size="16" aria-hidden="true" />
          <CheckCircle2 v-else :size="16" aria-hidden="true" />
        </span>
        <span class="notification-inbox__main">
          <strong>{{ row.title }}</strong>
          <small>{{ row.content }}</small>
          <span class="notification-inbox__meta"><time>{{ formatTime(row.scheduledAt) }}</time><em :title="row.deliveryDetail || undefined">{{ channelLabel(row.channel) }} · {{ statusLabel(row) }}</em></span>
        </span>
        <ExternalLink :size="15" aria-hidden="true" />
      </button>
    </div>
    <EmptyState v-else :text="t('notifications.empty')" />
  </BaseCard>
</template>

<style scoped>
.notification-inbox__hint { margin: -8px 0 12px; color: var(--color-text-muted); font-size: 12px; }
.notification-inbox__loading { min-height: 80px; }
.notification-inbox__list { display: grid; gap: 8px; }
.notification-inbox__row { display: grid; grid-template-columns: 30px minmax(0, 1fr) 16px; align-items: center; gap: 9px; width: 100%; padding: 10px; border: 1px solid var(--border-color); border-radius: 10px; background: #fff; color: var(--color-text); text-align: left; }
.notification-inbox__row:hover { border-color: #93c5fd; background: #eff6ff; }
.notification-inbox__row--critical { border-left: 3px solid #f97316; }
.notification-inbox__row--failed { border-left: 3px solid var(--color-danger); background: #fff7f7; }
.notification-inbox__row--info { border-left: 3px solid #60a5fa; }
.notification-inbox__icon { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 8px; background: #dbeafe; color: #1d4ed8; }
.notification-inbox__row--critical .notification-inbox__icon { background: #ffedd5; color: #c2410c; }
.notification-inbox__row--failed .notification-inbox__icon { background: #fee2e2; color: #b91c1c; }
.notification-inbox__main { display: grid; min-width: 0; gap: 3px; }
.notification-inbox__main strong, .notification-inbox__main small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.notification-inbox__main small { color: var(--color-text-muted); }
.notification-inbox__meta { display: flex; flex-wrap: wrap; gap: 8px; color: var(--color-text-muted); font-size: 11px; }
.notification-inbox__meta em { font-style: normal; }
</style>
