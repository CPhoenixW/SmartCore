<script setup lang="ts">
import { computed, ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import SmoothLineChart, { type CurveChartSeries } from "@/components/base/SmoothLineChart.vue";
import DeviceManagementPanel from "@/components/device/DeviceManagementPanel.vue";
import DeviceMetricStrip, { type DeviceMetric } from "@/components/device/DeviceMetricStrip.vue";
import DevicePairPanel from "@/components/device/DevicePairPanel.vue";
import FeishuBotManager from "@/components/device/FeishuBotManager.vue";
import { adminApi } from "@/api/admin";
import { feishuPairApi, type FeishuUsageRange } from "@/api/feishuPair";
import { useUserStore } from "@/stores/user";
import { formatDateTime } from "@/utils/date";

const { t, locale } = useI18n();
const userStore = useUserStore();
const range = ref<FeishuUsageRange>("today");
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai";
const isAdmin = computed(() => userStore.user.role === "admin");
const usage = useQuery({
  queryKey: ["feishuUsage", range, timezone],
  queryFn: () => feishuPairApi.usage(range.value, timezone),
  refetchInterval: 60_000,
});
const bindings = useQuery({ queryKey: ["userFeishuBindings"], queryFn: feishuPairApi.bindings, refetchInterval: 30_000 });
const bots = useQuery({ queryKey: ["feishuBots"], queryFn: adminApi.feishuBots, enabled: isAdmin, refetchInterval: 30_000 });
const report = computed(() => usage.data.value);
const enabledBots = computed(() => (bots.data.value ?? []).filter((bot) => bot.enabled));
const trendLabels = computed(() => (report.value?.trend ?? []).map((point) => trendLabel(point.startAt)));
const trendSeries = computed<CurveChartSeries[]>(() => [{
  key: "messages",
  name: t("feishuDevice.messages"),
  color: "#2563eb",
  values: (report.value?.trend ?? []).map((point) => point.messages),
}]);
const successRate = computed(() => {
  const total = (report.value?.totals.forwarded ?? 0) + (report.value?.totals.failed ?? 0);
  return total ? Math.round((report.value?.totals.forwarded ?? 0) / total * 100) : null;
});
const latestBinding = computed(() => [...(bindings.data.value ?? [])]
  .filter((binding) => binding.lastSeenAt)
  .sort((left, right) => String(right.lastSeenAt).localeCompare(String(left.lastSeenAt)))[0]);
const metrics = computed<DeviceMetric[]>(() => [
  {
    label: t("feishuDevice.botStatus"),
    value: isAdmin.value ? (enabledBots.value.length ? t("feishuDevice.running") : t("feishuDevice.disabled")) : ((bindings.data.value?.length ?? 0) ? t("feishuDevice.bound") : t("feishuDevice.unbound")),
    note: isAdmin.value ? t("feishuDevice.enabledBots", { count: enabledBots.value.length }) : t("feishuDevice.currentUser"),
    tone: enabledBots.value.length || bindings.data.value?.length ? "success" : "neutral",
  },
  {
    label: t("feishuDevice.messages"),
    value: String(report.value?.totals.messages ?? 0),
    note: t("feishuDevice.forwardedNote", { count: report.value?.totals.forwarded ?? 0 }),
  },
  {
    label: t("feishuDevice.successRate"),
    value: successRate.value == null ? t("common.notSet") : `${successRate.value}%`,
    note: t("feishuDevice.failureNote", { count: report.value?.totals.failed ?? 0 }),
    tone: successRate.value == null ? "neutral" : (report.value?.totals.failed ?? 0) > 0 ? "warning" : "success",
  },
  {
    label: t("feishuDevice.bindings"),
    value: String(bindings.data.value?.length ?? 0),
    note: latestBinding.value?.lastSeenAt ? t("feishuDevice.lastMessageAt", { value: timeLabel(latestBinding.value.lastSeenAt) }) : t("feishuDevice.noRecentMessage"),
    tone: "neutral",
  },
]);

function timeLabel(value: string) {
  return new Date(value).toLocaleTimeString(locale.value === "en-US" ? "en-US" : "zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
}
function trendLabel(value: string) {
  const date = new Date(value);
  return range.value === "today" ? timeLabel(value) : date.toLocaleDateString(locale.value === "en-US" ? "en-US" : "zh-CN", { month: "2-digit", day: "2-digit" });
}
function statusLabel(value?: string | null) {
  if (value === "forwarded") return t("feishuDevice.status.forwarded");
  if (value === "forward_failed") return t("feishuDevice.status.failed");
  if (value?.startsWith("unsupported:")) return t("feishuDevice.status.unsupported");
  return value || t("common.notSet");
}
function intentLabel(value?: string | null) {
  if (value === "openclaw_forward") return t("feishuDevice.intent.message");
  if (value === "unsupported_message") return t("feishuDevice.intent.unsupported");
  return t("feishuDevice.intent.other");
}
function percentage(value: number, total: number) {
  return total > 0 ? value / total * 100 : 0;
}
</script>

<template>
  <div class="device-data-page">
    <div class="device-range-toolbar">
      <span>{{ t("feishuDevice.range") }}</span>
      <div class="segmented" role="group" :aria-label="t('feishuDevice.range')">
        <button v-for="item in (['today', '7d', '30d'] as FeishuUsageRange[])" :key="item" type="button" :class="{ active: range === item }" @click="range = item">{{ t(`computer.rangeOption.${item}`) }}</button>
      </div>
    </div>

    <DeviceMetricStrip :items="metrics" :label="t('feishuDevice.dataSummary')" />

    <section class="device-data-grid device-data-grid--matched device-data-grid--feishu-summary">
      <BaseCard :title="t('feishuDevice.messageTrend')" :subtitle="t('feishuDevice.messageTrendNote')">
        <SmoothLineChart v-if="report?.totals.messages" :labels="trendLabels" :series="trendSeries" :label="t('feishuDevice.messageTrend')" />
        <EmptyState v-else :text="t('feishuDevice.noMessages')" />
      </BaseCard>

      <BaseCard :title="t('feishuDevice.results')">
        <div class="feishu-result-list">
          <div><span>{{ t("feishuDevice.status.forwarded") }}</span><strong>{{ report?.totals.forwarded ?? 0 }}</strong><i><b :style="{ width: `${percentage(report?.totals.forwarded ?? 0, report?.totals.messages ?? 0)}%` }" /></i></div>
          <div><span>{{ t("feishuDevice.status.failed") }}</span><strong>{{ report?.totals.failed ?? 0 }}</strong><i><b class="failed" :style="{ width: `${percentage(report?.totals.failed ?? 0, report?.totals.messages ?? 0)}%` }" /></i></div>
          <div><span>{{ t("feishuDevice.status.unsupported") }}</span><strong>{{ report?.totals.unsupported ?? 0 }}</strong><i><b class="unsupported" :style="{ width: `${percentage(report?.totals.unsupported ?? 0, report?.totals.messages ?? 0)}%` }" /></i></div>
          <div><span>{{ t("feishuDevice.notifications") }}</span><strong>{{ report?.totals.notificationsSent ?? 0 }}</strong><i><b class="notification" :style="{ width: `${percentage(report?.totals.notificationsSent ?? 0, (report?.totals.notificationsSent ?? 0) + (report?.totals.notificationsFailed ?? 0))}%` }" /></i></div>
        </div>
      </BaseCard>
    </section>

    <section class="device-data-grid device-data-grid--equal device-data-grid--scroll-pair device-data-grid--feishu-activity">
      <BaseCard :title="t('feishuDevice.recentMessages')">
        <div v-if="report?.recent.length" class="device-activity-list device-scroll-list">
          <article v-for="item in report.recent" :key="item.msgId"><time>{{ formatDateTime(item.createdAt, locale === 'en-US' ? 'en-US' : 'zh-CN') }}</time><div><strong>{{ intentLabel(item.intent) }}</strong><small>{{ statusLabel(item.stat) }}</small></div><span class="device-status-text" :class="{ 'device-status-text--warning': item.stat !== 'forwarded' }">{{ statusLabel(item.stat) }}</span></article>
        </div>
        <EmptyState v-else :text="t('feishuDevice.noMessages')" />
      </BaseCard>
      <BaseCard :title="t('feishuDevice.bindingStatus')">
        <div v-if="bindings.data.value?.length" class="device-activity-list device-scroll-list">
          <article v-for="binding in bindings.data.value" :key="binding.bindId"><time>{{ binding.chatType }}</time><div><strong>{{ binding.botName }}</strong><small>{{ binding.chatHint }}</small></div><span class="device-status-text">{{ binding.isPrimary ? t("feishuDevice.primaryBinding") : t("feishuDevice.activeBinding") }}</span></article>
        </div>
        <EmptyState v-else :text="t('feishuDevice.noBindings')" />
      </BaseCard>
    </section>

    <DeviceManagementPanel icon="飞" :title="t('feishuDevice.managementTitle')" :summary="t('feishuDevice.managementSummary', { count: bindings.data.value?.length ?? 0 })">
      <FeishuBotManager v-if="isAdmin" embedded />
      <DevicePairPanel v-else embedded :allowed-kinds="['feishuBot']" :title="t('feishuDevice.pairTitle')" />
    </DeviceManagementPanel>
  </div>
</template>

<style scoped>
.device-range-toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;color:var(--color-text-muted);font-size:12px}
@media(max-width:640px){.device-range-toolbar{align-items:stretch;flex-direction:column;gap:8px}.device-range-toolbar .segmented{width:100%}}
</style>
