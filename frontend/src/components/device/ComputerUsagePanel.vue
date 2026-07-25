<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import DevicePairPanel from "@/components/device/DevicePairPanel.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import { computerApi } from "@/api/computer";
import { deviceRegistryApi } from "@/api/deviceRegistry";
import type { ComputerRange, ComputerSession } from "@/types/computer";
import { dominantComputerState, durationLabel, timelinePosition } from "@/utils/computer";
import { formatDateTime } from "@/utils/date";

const { t, locale } = useI18n();
const range = ref<ComputerRange>("today");
const selectedDeviceId = ref("");
const selectedSession = ref<ComputerSession | null>(null);
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai";
const devices = useQuery({ queryKey: ["lifeDevices"], queryFn: deviceRegistryApi.list, refetchInterval: 15_000 });
const computers = computed(() => (devices.data.value ?? []).filter((item) => item.deviceKind === "computer" && item.stat === "active"));
watch(computers, (items) => {
  if (!items.some((item) => item.deviceId === selectedDeviceId.value)) selectedDeviceId.value = items[0]?.deviceId ?? "";
}, { immediate: true });
const enabled = computed(() => Boolean(selectedDeviceId.value));
const status = useQuery({
  queryKey: ["computer", "status", selectedDeviceId],
  queryFn: () => computerApi.status(selectedDeviceId.value),
  enabled,
  refetchInterval: 10_000,
});
const usage = useQuery({
  queryKey: ["computer", "usage", selectedDeviceId, range, timezone],
  queryFn: () => computerApi.usage(selectedDeviceId.value, range.value, timezone),
  enabled,
  refetchInterval: 60_000,
});
const report = computed(() => usage.data.value);
const monitor = computed(() => status.data.value ?? report.value?.status ?? null);
const maxDaily = computed(() => Math.max(1, ...(report.value?.daily ?? []).map((item) => Math.max(item.activeSeconds, item.plannedActiveSeconds))));
const maxApp = computed(() => Math.max(1, ...(report.value?.applications ?? []).map((item) => item.seconds)));

function stateLabel(state: string) { return t(`computer.state.${state}`); }
function analysisLabel(state: string) { return t(`computer.analysisState.${state}`); }
function analysisBasis() {
  const analysis = monitor.value?.analysis;
  if (!analysis) return t("common.notSet");
  if (analysis.currentPlan) return analysis.currentPlan.title;
  if (analysis.presence?.present === true) return t("computer.analysisPresencePresent");
  if (analysis.presence?.present === false) return t("computer.analysisPresenceAway");
  return t("computer.analysisComputerOnly");
}
function timeLabel(value: string) {
  return new Date(value).toLocaleTimeString(locale.value === "en-US" ? "en-US" : "zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
}
function currentDuration() {
  if (!monitor.value?.stateSince) return t("common.notSet");
  return durationLabel((Date.now() - new Date(monitor.value.stateSince).getTime()) / 1000);
}
function minuteStyle(startAt: string) {
  if (!report.value) return {};
  return timelinePosition(startAt, new Date(new Date(startAt).getTime() + 60_000).toISOString(), report.value.windowStart, report.value.windowEnd);
}
function intervalStyle(startAt: string, endAt: string) {
  if (!report.value) return {};
  return timelinePosition(startAt, endAt, report.value.windowStart, report.value.windowEnd);
}
</script>

<template>
  <div class="computer-panel">
    <DevicePairPanel :allowed-kinds="['computer']" :title="t('computer.pairTitle')" />
    <template v-if="computers.length">
      <div class="computer-toolbar">
        <label><span>{{ t("computer.device") }}</span><select v-model="selectedDeviceId"><option v-for="item in computers" :key="item.deviceId" :value="item.deviceId">{{ item.deviceName }}</option></select></label>
        <div class="segmented" role="group" :aria-label="t('computer.range')"><button v-for="item in (['today', '7d', '30d'] as ComputerRange[])" :key="item" type="button" :class="{ active: range === item }" @click="range = item">{{ t(`computer.rangeOption.${item}`) }}</button></div>
      </div>

      <div v-if="monitor && (monitor.paused || monitor.state === 'offline' || monitor.queueDepth > 5)" class="computer-alert" :class="`computer-alert--${monitor.state}`">
        <strong v-if="monitor.paused">{{ t("computer.paused") }}</strong>
        <strong v-else-if="monitor.state === 'offline'">{{ t("computer.offline") }}</strong>
        <strong v-else>{{ t("computer.syncDelayed", { count: monitor.queueDepth }) }}</strong>
      </div>

      <BaseCard :title="t('computer.current')">
        <div v-if="monitor" class="computer-current">
          <span class="computer-state-dot" :class="`computer-state-dot--${monitor.state}`" />
          <div class="computer-current__identity"><strong>{{ stateLabel(monitor.state) }}</strong><span>{{ currentDuration() }}</span></div>
          <div><span>{{ t("computer.context") }}</span><strong>{{ monitor.currentAppName || t("common.notSet") }}</strong></div>
          <div><span>{{ t("computer.analysis") }}</span><strong>{{ analysisLabel(monitor.analysis.state) }}</strong><small>{{ analysisBasis() }}</small></div>
          <div><span>{{ t("computer.lastSync") }}</span><strong>{{ formatDateTime(monitor.lastHeartbeatAt) }}</strong><small>{{ t("computer.queue", { count: monitor.queueDepth }) }}</small></div>
        </div>
        <EmptyState v-else :text="t('computer.waitingHeartbeat')" />
      </BaseCard>

      <section v-if="report" class="computer-metrics" aria-label="Computer activity totals">
        <article><span>{{ t("computer.activeTime") }}</span><strong>{{ durationLabel(report.totals.activeSeconds) }}</strong></article>
        <article><span>{{ t("computer.plannedActive") }}</span><strong>{{ durationLabel(report.totals.plannedActiveSeconds) }}</strong></article>
        <article><span>{{ t("computer.idleTime") }}</span><strong>{{ durationLabel(report.totals.idleSeconds) }}</strong></article>
        <article><span>{{ t("computer.switches") }}</span><strong>{{ report.totals.switchCount }}</strong></article>
      </section>

      <BaseCard v-if="range === 'today'" :title="t('computer.timeline')">
        <div v-if="report?.timeline.length" class="activity-timeline">
          <div class="timeline-axis"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>{{ timeLabel(report.windowEnd) }}</span></div>
          <div class="timeline-row"><strong>{{ t("computer.plans") }}</strong><div class="timeline-track"><i v-for="plan in report.plans" :key="plan.evtId" class="timeline-block timeline-block--plan" :style="intervalStyle(plan.startAt, plan.endAt)" :title="`${plan.title} · ${durationLabel(plan.activeSeconds)}`" /></div></div>
          <div class="timeline-row"><strong>{{ t("computer.statusLane") }}</strong><div class="timeline-track"><i v-for="point in report.timeline" :key="`state-${point.startAt}`" class="timeline-block" :class="`timeline-block--${dominantComputerState(point)}`" :style="minuteStyle(point.startAt)" :title="stateLabel(dominantComputerState(point))" /></div></div>
          <div class="timeline-row"><strong>{{ t("computer.appLane") }}</strong><div class="timeline-track"><i v-for="point in report.timeline.filter((item) => item.dominantContext)" :key="`app-${point.startAt}`" class="timeline-block timeline-block--app" :style="minuteStyle(point.startAt)" :title="point.dominantContext?.appName" /></div></div>
        </div>
        <EmptyState v-else :text="t('computer.noUsage')" />
      </BaseCard>

      <div v-if="range === 'today'" class="computer-two-column">
        <BaseCard :title="t('computer.sessions')">
          <div v-if="report?.sessions.length" class="session-list">
            <button v-for="session in report.sessions" :key="session.sessionId" type="button" @click="selectedSession = session">
              <span><strong>{{ timeLabel(session.startAt) }}–{{ timeLabel(session.endAt) }}</strong><small>{{ session.contexts[0]?.appName || t("common.notSet") }}</small></span>
              <span><strong>{{ durationLabel(session.activeSeconds) }}</strong><small>{{ t("computer.sessionMeta", { switches: session.switchCount, planned: durationLabel(session.plannedActiveSeconds) }) }}</small></span>
            </button>
          </div>
          <EmptyState v-else :text="t('computer.noSessions')" />
        </BaseCard>
        <BaseCard :title="t('computer.applications')">
          <div v-if="report?.applications.length" class="app-ranking"><div v-for="app in report.applications" :key="app.bundleId"><span><strong>{{ app.appName }}</strong><small>{{ durationLabel(app.seconds) }}</small></span><i><b :style="{ width: `${app.seconds / maxApp * 100}%` }" /></i></div></div>
          <EmptyState v-else :text="t('computer.noUsage')" />
        </BaseCard>
      </div>

      <div v-else class="computer-two-column">
        <BaseCard :title="t('computer.dailyTrend')">
          <div v-if="report?.daily.length" class="daily-chart"><div v-for="day in report.daily" :key="day.date"><div class="daily-bars"><i :style="{ height: `${day.activeSeconds / maxDaily * 100}%` }" :title="`${t('computer.activeTime')} ${durationLabel(day.activeSeconds)}`" /><i :style="{ height: `${day.plannedActiveSeconds / maxDaily * 100}%` }" :title="`${t('computer.plannedActive')} ${durationLabel(day.plannedActiveSeconds)}`" /></div><small>{{ day.date.slice(5) }}</small></div></div>
          <EmptyState v-else :text="t('computer.noUsage')" />
        </BaseCard>
        <BaseCard :title="t('computer.applications')">
          <div v-if="report?.applications.length" class="app-ranking"><div v-for="app in report.applications" :key="app.bundleId"><span><strong>{{ app.appName }}</strong><small>{{ durationLabel(app.seconds) }}</small></span><i><b :style="{ width: `${app.seconds / maxApp * 100}%` }" /></i></div></div>
          <EmptyState v-else :text="t('computer.noUsage')" />
        </BaseCard>
      </div>
    </template>
    <EmptyState v-else :text="t('computer.noDevice')" />

    <div v-if="selectedSession" class="session-drawer-backdrop" @click.self="selectedSession = null">
      <aside class="session-drawer" role="dialog" aria-modal="true" :aria-label="t('computer.sessionDetail')">
        <header><div><h2>{{ t("computer.sessionDetail") }}</h2><p>{{ timeLabel(selectedSession.startAt) }}–{{ timeLabel(selectedSession.endAt) }}</p></div><button class="icon-button" type="button" :aria-label="t('common.close')" @click="selectedSession = null">×</button></header>
        <dl><div><dt>{{ t("computer.activeTime") }}</dt><dd>{{ durationLabel(selectedSession.activeSeconds) }}</dd></div><div><dt>{{ t("computer.plannedActive") }}</dt><dd>{{ durationLabel(selectedSession.plannedActiveSeconds) }}</dd></div><div><dt>{{ t("computer.switches") }}</dt><dd>{{ selectedSession.switchCount }}</dd></div></dl>
        <div class="session-contexts"><article v-for="context in selectedSession.contexts" :key="context.contextId"><div><strong>{{ context.appName }}</strong><small>{{ context.bundleId }}</small></div><span>{{ durationLabel(context.seconds) }}</span></article></div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.computer-panel{grid-auto-rows:max-content;align-content:start}
.computer-panel{display:grid;gap:18px}.computer-toolbar{display:flex;align-items:end;justify-content:space-between;gap:16px}.computer-toolbar label{display:grid;min-width:240px;gap:6px;color:var(--color-text-muted);font-size:12px}.computer-toolbar select{min-height:40px;padding:0 11px;border:1px solid var(--border-color);border-radius:7px;background:#fff;color:var(--color-text);font:inherit}.segmented{display:flex;padding:3px;border:1px solid var(--border-color);border-radius:8px;background:#f8fafc}.segmented button{min-width:64px;padding:7px 11px;border:0;border-radius:5px;background:transparent;color:#64748b}.segmented button.active{background:#fff;color:#111827;box-shadow:0 1px 4px rgb(15 23 42 / 12%)}.computer-alert{padding:12px 14px;border-left:4px solid #d97706;background:#fffbeb;color:#92400e}.computer-alert--offline,.computer-alert--paused{border-left-color:#64748b;background:#f8fafc;color:#475569}.computer-current{display:grid;grid-template-columns:auto minmax(120px,.65fr) minmax(180px,1.4fr) minmax(160px,1fr) minmax(130px,.8fr);align-items:center;gap:16px}.computer-current>div:not(.computer-current__identity) span,.computer-current small,.computer-current__identity span{display:block;color:var(--color-text-muted);font-size:12px}.computer-current>div strong{display:block;margin:4px 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.computer-state-dot{width:18px;height:18px;border-radius:50%;background:#94a3b8}.computer-state-dot--active{background:#16a34a}.computer-state-dot--idle{background:#d97706}.computer-state-dot--locked,.computer-state-dot--sleeping{background:#475569}.computer-state-dot--paused{background:#2563eb}.computer-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid var(--border-color);border-radius:8px;background:#fff}.computer-metrics article{padding:18px;border-right:1px solid var(--border-color)}.computer-metrics article:last-child{border:0}.computer-metrics span{display:block;color:var(--color-text-muted);font-size:12px}.computer-metrics strong{display:block;margin-top:6px;font-size:25px}.activity-timeline{display:grid;gap:10px;overflow-x:auto}.timeline-axis{display:flex;justify-content:space-between;margin-left:104px;color:#94a3b8;font-size:10px}.timeline-row{display:grid;grid-template-columns:94px minmax(650px,1fr);align-items:center;gap:10px}.timeline-row>strong{font-size:12px}.timeline-track{position:relative;height:28px;overflow:hidden;border:1px solid #e2e8f0;border-radius:4px;background:repeating-linear-gradient(90deg,#f8fafc 0,#f8fafc calc(25% - 1px),#e2e8f0 25%)}.timeline-block{position:absolute;top:3px;height:20px;min-width:2px;border-radius:2px;background:#94a3b8}.timeline-block--plan{top:4px;height:18px;background:#2563eb}.timeline-block--active{background:#16a34a}.timeline-block--idle{background:#d97706}.timeline-block--locked{background:#475569}.timeline-block--sleeping{background:#0f172a}.timeline-block--paused{background:#0ea5e9}.timeline-block--app{background:#7c3aed}.computer-two-column{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(320px,.75fr);gap:18px}.session-list{display:grid}.session-list button{display:flex;align-items:center;justify-content:space-between;gap:16px;width:100%;padding:13px 2px;border:0;border-bottom:1px solid var(--border-color);background:#fff;text-align:left}.session-list button:hover{background:#f8fafc}.session-list span:last-child{text-align:right}.session-list strong,.session-list small{display:block}.session-list small{margin-top:4px;color:var(--color-text-muted);font-size:11px}.app-ranking{display:grid;gap:13px}.app-ranking>div{display:grid;gap:6px}.app-ranking span{display:flex;justify-content:space-between;gap:12px}.app-ranking small{color:var(--color-text-muted)}.app-ranking i{height:6px;overflow:hidden;border-radius:3px;background:#e2e8f0}.app-ranking b{display:block;height:100%;background:#7c3aed}.daily-chart{display:flex;align-items:end;gap:7px;height:220px;overflow-x:auto;padding-top:16px}.daily-chart>div{display:grid;grid-template-rows:180px auto;min-width:30px;flex:1;gap:7px;text-align:center}.daily-bars{display:flex;align-items:end;justify-content:center;gap:3px}.daily-bars i{width:8px;min-height:2px;background:#16a34a}.daily-bars i+ i{background:#2563eb}.daily-chart small{color:#64748b;font-size:9px}.session-drawer-backdrop{position:fixed;inset:0;z-index:80;background:rgb(15 23 42 / 35%)}.session-drawer{position:absolute;inset:0 0 0 auto;width:min(460px,100%);overflow:auto;padding:24px;background:#fff;box-shadow:-14px 0 30px rgb(15 23 42 / 18%)}.session-drawer header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding-bottom:18px;border-bottom:1px solid var(--border-color)}.session-drawer header p{margin-top:5px;color:var(--color-text-muted)}.session-drawer dl{display:grid;grid-template-columns:repeat(3,1fr);margin:18px 0;border:1px solid var(--border-color);border-radius:8px}.session-drawer dl div{padding:12px}.session-drawer dt{color:var(--color-text-muted);font-size:11px}.session-drawer dd{margin:5px 0 0;font-weight:700}.session-contexts{display:grid}.session-contexts article{display:flex;justify-content:space-between;gap:16px;padding:13px 0;border-bottom:1px solid var(--border-color)}.session-contexts strong,.session-contexts small{display:block}.session-contexts small{margin-top:4px;color:var(--color-text-muted);overflow-wrap:anywhere}@media(max-width:900px){.computer-current{grid-template-columns:auto 1fr}.computer-current>div:not(.computer-current__identity){grid-column:1/-1}.computer-two-column{grid-template-columns:1fr}}@media(max-width:640px){.computer-toolbar{align-items:stretch;flex-direction:column}.computer-toolbar label{min-width:0}.segmented button{min-width:0;flex:1}.computer-metrics{grid-template-columns:1fr 1fr}.computer-metrics article:nth-child(2){border-right:0}.computer-metrics article:nth-child(-n+2){border-bottom:1px solid var(--border-color)}.session-list button{align-items:flex-start;flex-direction:column}.session-list span:last-child{text-align:left}.session-drawer dl{grid-template-columns:1fr}}
</style>
