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
import { dominantComputerState, durationLabel, timelinePosition, timelineTicks } from "@/utils/computer";
import { formatDateTime } from "@/utils/date";

const APP_COLORS = ["#2563eb", "#7c3aed", "#0891b2", "#db2777", "#d97706", "#16a34a"];
const OBJECTIVE_STATES = ["active", "idle", "locked", "sleeping", "paused"] as const;

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
const axisTicks = computed(() => report.value ? timelineTicks(report.value.windowStart, report.value.windowEnd) : []);

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
function duration(seconds: number) {
  return durationLabel(seconds, locale.value === "en-US" ? "en-US" : "zh-CN");
}
function currentDuration() {
  if (!monitor.value?.stateSince) return t("common.notSet");
  return duration((Date.now() - new Date(monitor.value.stateSince).getTime()) / 1000);
}
function minuteStyle(startAt: string) {
  if (!report.value) return {};
  return timelinePosition(startAt, new Date(new Date(startAt).getTime() + 60_000).toISOString(), report.value.windowStart, report.value.windowEnd);
}
function intervalStyle(startAt: string, endAt: string) {
  if (!report.value) return {};
  return timelinePosition(startAt, endAt, report.value.windowStart, report.value.windowEnd);
}
function stableColor(value: string) {
  let hash = 0;
  for (const char of value) hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0;
  return APP_COLORS[Math.abs(hash) % APP_COLORS.length];
}
function appInitial(value?: string | null) {
  return (value?.trim().charAt(0) || "?").toUpperCase();
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

      <div class="computer-overview-grid">
        <BaseCard :title="t('computer.current')">
          <div v-if="monitor" class="computer-current">
            <div class="computer-status-hero">
              <span class="computer-state-dot" :class="`computer-state-dot--${monitor.state}`" />
              <div><strong>{{ stateLabel(monitor.state) }}</strong><span>{{ currentDuration() }}</span></div>
              <b v-if="monitor.currentAppName">{{ monitor.currentAppName }}</b>
            </div>
            <div class="computer-parameter-grid">
              <div><span>{{ t("computer.analysis") }}</span><strong>{{ analysisLabel(monitor.analysis.state) }}</strong><small>{{ analysisBasis() }}</small></div>
              <div><span>{{ t("computer.lastSync") }}</span><strong>{{ formatDateTime(monitor.lastHeartbeatAt, locale === 'en-US' ? 'en-US' : 'zh-CN') }}</strong><small>{{ t("computer.queue", { count: monitor.queueDepth }) }}</small></div>
              <div><span>{{ t("computer.permission") }}</span><strong>{{ monitor.accessibilityGranted ? t("computer.granted") : t("computer.notGranted") }}</strong><small>{{ monitor.appVersion || t("common.notSet") }}</small></div>
            </div>
          </div>
          <EmptyState v-else :text="t('computer.waitingHeartbeat')" />
        </BaseCard>

        <BaseCard :title="t('computer.activitySummary')">
          <section v-if="report" class="computer-metrics" aria-label="Computer activity totals">
            <article class="metric--active"><span>{{ t("computer.activeTime") }}</span><strong>{{ duration(report.totals.activeSeconds) }}</strong></article>
            <article class="metric--planned"><span>{{ t("computer.plannedActive") }}</span><strong>{{ duration(report.totals.plannedActiveSeconds) }}</strong></article>
            <article class="metric--idle"><span>{{ t("computer.idleTime") }}</span><strong>{{ duration(report.totals.idleSeconds) }}</strong></article>
            <article class="metric--switch"><span>{{ t("computer.switches") }}</span><strong>{{ report.totals.switchCount }}</strong></article>
          </section>
          <EmptyState v-else :text="t('computer.noUsage')" />
        </BaseCard>
      </div>

      <BaseCard v-if="range === 'today'" :title="t('computer.timeline')">
        <div v-if="report?.timeline.length" class="activity-timeline">
          <div class="timeline-legend">
            <span v-for="state in OBJECTIVE_STATES" :key="state"><i :class="`timeline-key timeline-key--${state}`" />{{ stateLabel(state) }}</span>
          </div>
          <div class="timeline-axis"><span v-for="tick in axisTicks" :key="tick">{{ timeLabel(tick) }}</span></div>
          <div class="timeline-row">
            <strong>{{ t("computer.plans") }}</strong>
            <div class="timeline-track"><i v-for="plan in report.plans" :key="plan.evtId" class="timeline-block timeline-block--plan" :style="intervalStyle(plan.startAt, plan.endAt)" :title="`${plan.title} · ${duration(plan.activeSeconds)}`" /><span v-if="!report.plans.length" class="timeline-empty">{{ t("computer.noPlans") }}</span></div>
          </div>
          <div class="timeline-row">
            <strong>{{ t("computer.statusLane") }}</strong>
            <div class="timeline-track"><i v-for="point in report.timeline" :key="`state-${point.startAt}`" class="timeline-block" :class="`timeline-block--${dominantComputerState(point)}`" :style="minuteStyle(point.startAt)" :title="`${timeLabel(point.startAt)} · ${stateLabel(dominantComputerState(point))}`" /></div>
          </div>
          <div class="timeline-row">
            <strong>{{ t("computer.appLane") }}</strong>
            <div class="timeline-track"><i v-for="point in report.timeline.filter((item) => item.dominantContext)" :key="`app-${point.startAt}`" class="timeline-block timeline-block--app" :style="{ ...minuteStyle(point.startAt), background: stableColor(point.dominantContext?.bundleId || point.dominantContext?.contextId || '') }" :title="`${timeLabel(point.startAt)} · ${point.dominantContext?.appName}`" /></div>
          </div>
        </div>
        <EmptyState v-else :text="t('computer.noUsage')" />
      </BaseCard>

      <div v-if="range === 'today'" class="computer-two-column">
        <BaseCard :title="t('computer.sessions')">
          <div v-if="report?.sessions.length" class="session-list">
            <button v-for="session in report.sessions" :key="session.sessionId" type="button" @click="selectedSession = session">
              <i class="session-app-mark" :style="{ background: stableColor(session.contexts[0]?.bundleId || session.sessionId) }">{{ appInitial(session.contexts[0]?.appName) }}</i>
              <span class="session-main"><strong>{{ session.contexts[0]?.appName || t("common.notSet") }}</strong><small>{{ timeLabel(session.startAt) }}–{{ timeLabel(session.endAt) }}</small></span>
              <span class="session-summary"><strong>{{ duration(session.activeSeconds) }}</strong><small>{{ t("computer.sessionMeta", { switches: session.switchCount, planned: duration(session.plannedActiveSeconds) }) }}</small></span>
            </button>
          </div>
          <EmptyState v-else :text="t('computer.noSessions')" />
        </BaseCard>
        <BaseCard :title="t('computer.applications')">
          <div v-if="report?.applications.length" class="app-ranking"><div v-for="(app, index) in report.applications" :key="app.bundleId"><span class="app-ranking__label"><b>{{ index + 1 }}</b><strong>{{ app.appName }}</strong><small>{{ duration(app.seconds) }}</small></span><i><b :style="{ width: `${app.seconds / maxApp * 100}%`, background: stableColor(app.bundleId) }" /></i></div></div>
          <EmptyState v-else :text="t('computer.noUsage')" />
        </BaseCard>
      </div>

      <div v-else class="computer-two-column">
        <BaseCard :title="t('computer.dailyTrend')">
          <div v-if="report?.daily.length" class="daily-chart"><div v-for="day in report.daily" :key="day.date"><div class="daily-bars"><i :style="{ height: `${day.activeSeconds / maxDaily * 100}%` }" :title="`${t('computer.activeTime')} ${duration(day.activeSeconds)}`" /><i :style="{ height: `${day.plannedActiveSeconds / maxDaily * 100}%` }" :title="`${t('computer.plannedActive')} ${duration(day.plannedActiveSeconds)}`" /></div><small>{{ day.date.slice(5) }}</small></div></div>
          <EmptyState v-else :text="t('computer.noUsage')" />
        </BaseCard>
        <BaseCard :title="t('computer.applications')">
          <div v-if="report?.applications.length" class="app-ranking"><div v-for="(app, index) in report.applications" :key="app.bundleId"><span class="app-ranking__label"><b>{{ index + 1 }}</b><strong>{{ app.appName }}</strong><small>{{ duration(app.seconds) }}</small></span><i><b :style="{ width: `${app.seconds / maxApp * 100}%`, background: stableColor(app.bundleId) }" /></i></div></div>
          <EmptyState v-else :text="t('computer.noUsage')" />
        </BaseCard>
      </div>
    </template>
    <EmptyState v-else :text="t('computer.noDevice')" />

    <div v-if="selectedSession" class="session-drawer-backdrop" @click.self="selectedSession = null">
      <aside class="session-drawer" role="dialog" aria-modal="true" :aria-label="t('computer.sessionDetail')">
        <header><div><h2>{{ t("computer.sessionDetail") }}</h2><p>{{ timeLabel(selectedSession.startAt) }}–{{ timeLabel(selectedSession.endAt) }}</p></div><button class="icon-button" type="button" :aria-label="t('common.close')" @click="selectedSession = null">×</button></header>
        <dl><div><dt>{{ t("computer.activeTime") }}</dt><dd>{{ duration(selectedSession.activeSeconds) }}</dd></div><div><dt>{{ t("computer.plannedActive") }}</dt><dd>{{ duration(selectedSession.plannedActiveSeconds) }}</dd></div><div><dt>{{ t("computer.switches") }}</dt><dd>{{ selectedSession.switchCount }}</dd></div></dl>
        <div class="session-contexts"><article v-for="context in selectedSession.contexts" :key="context.contextId"><div><strong>{{ context.appName }}</strong><small>{{ [context.domain, context.workspace, context.documentName, context.windowTitle, context.bundleId].filter(Boolean).join(' · ') }}</small></div><span>{{ duration(context.seconds) }}</span></article></div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.computer-panel{display:grid;grid-auto-rows:max-content;align-content:start;gap:18px}.computer-toolbar{display:flex;align-items:end;justify-content:space-between;gap:16px}.computer-toolbar label{display:grid;min-width:240px;gap:6px;color:var(--color-text-muted);font-size:12px}.computer-toolbar select{min-height:40px;padding:0 11px;border:1px solid var(--border-color);border-radius:7px;background:#fff;color:var(--color-text);font:inherit}.segmented{display:flex;padding:3px;border:1px solid var(--border-color);border-radius:8px;background:#f8fafc}.segmented button{min-width:64px;padding:7px 11px;border:0;border-radius:5px;background:transparent;color:#64748b}.segmented button.active{background:#fff;color:#111827;box-shadow:0 1px 4px rgb(15 23 42 / 12%)}.computer-alert{padding:12px 14px;border-left:4px solid #d97706;background:#fffbeb;color:#92400e}.computer-alert--offline,.computer-alert--paused{border-left-color:#64748b;background:#f8fafc;color:#475569}.computer-overview-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(360px,.85fr);gap:18px}.computer-current{display:grid;gap:18px}.computer-status-hero{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:13px}.computer-status-hero div strong,.computer-status-hero div span{display:block}.computer-status-hero div strong{font-size:24px}.computer-status-hero div span{margin-top:3px;color:var(--color-text-muted);font-size:12px}.computer-status-hero>b{max-width:220px;overflow:hidden;padding:7px 10px;border-radius:6px;background:#ecfdf5;color:#166534;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.computer-state-dot{width:20px;height:20px;border:5px solid #e2e8f0;border-radius:50%;background:#94a3b8;box-sizing:content-box}.computer-state-dot--active{border-color:#dcfce7;background:#16a34a}.computer-state-dot--idle{border-color:#fef3c7;background:#d97706}.computer-state-dot--locked,.computer-state-dot--sleeping{border-color:#e2e8f0;background:#475569}.computer-state-dot--paused{border-color:#dbeafe;background:#2563eb}.computer-parameter-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.computer-parameter-grid>div{min-width:0;padding:11px;border-radius:7px;background:#f8fafc}.computer-parameter-grid span,.computer-parameter-grid strong,.computer-parameter-grid small{display:block}.computer-parameter-grid span,.computer-parameter-grid small{color:var(--color-text-muted);font-size:11px}.computer-parameter-grid strong{margin:5px 0;overflow:hidden;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.computer-metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.computer-metrics article{position:relative;min-height:82px;overflow:hidden;padding:14px 14px 14px 17px;border-radius:7px;background:#f8fafc}.computer-metrics article::before{position:absolute;inset:0 auto 0 0;width:4px;background:#16a34a;content:""}.computer-metrics .metric--planned::before{background:#2563eb}.computer-metrics .metric--idle::before{background:#d97706}.computer-metrics .metric--switch::before{background:#7c3aed}.computer-metrics span{display:block;color:var(--color-text-muted);font-size:12px}.computer-metrics strong{display:block;margin-top:7px;font-size:22px}.activity-timeline{display:grid;gap:10px;overflow-x:auto;padding-top:2px}.timeline-legend{display:flex;justify-content:flex-end;flex-wrap:wrap;gap:12px;margin-left:106px;color:#64748b;font-size:10px}.timeline-legend span{display:flex;align-items:center;gap:5px}.timeline-key{width:8px;height:8px;border-radius:2px;background:#94a3b8}.timeline-key--active{background:#16a34a}.timeline-key--idle{background:#d97706}.timeline-key--locked{background:#64748b}.timeline-key--sleeping{background:#0f172a}.timeline-key--paused{background:#0ea5e9}.timeline-axis{display:flex;justify-content:space-between;min-width:680px;margin-left:106px;color:#94a3b8;font-size:10px}.timeline-row{display:grid;grid-template-columns:96px minmax(680px,1fr);align-items:center;gap:10px}.timeline-row>strong{font-size:12px}.timeline-track{position:relative;height:34px;overflow:hidden;border:1px solid #e2e8f0;border-radius:6px;background:repeating-linear-gradient(90deg,#f8fafc 0,#f8fafc calc(25% - 1px),#e2e8f0 25%)}.timeline-block{position:absolute;top:5px;height:22px;min-width:2px;border-radius:3px;background:#94a3b8}.timeline-block--plan{background:#2563eb}.timeline-block--active{background:#16a34a}.timeline-block--idle{background:#d97706}.timeline-block--locked{background:#64748b}.timeline-block--sleeping{background:#0f172a}.timeline-block--paused{background:#0ea5e9}.timeline-block--app{background:#7c3aed}.timeline-empty{position:absolute;inset:0;display:grid;place-items:center;color:#94a3b8;font-size:10px}.computer-two-column{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(320px,.75fr);gap:18px}.session-list{display:grid;gap:7px}.session-list button{display:grid;grid-template-columns:36px minmax(0,1fr) auto;align-items:center;gap:11px;width:100%;padding:10px;border:1px solid #eef2f7;border-radius:7px;background:#fff;text-align:left}.session-list button:hover{border-color:#bfdbfe;background:#f8fbff}.session-app-mark{display:grid;width:34px;height:34px;place-items:center;border-radius:7px;color:#fff;font-size:13px;font-style:normal;font-weight:800}.session-main strong,.session-main small,.session-summary strong,.session-summary small{display:block}.session-main strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.session-main small,.session-summary small{margin-top:3px;color:var(--color-text-muted);font-size:10px}.session-summary{text-align:right}.app-ranking{display:grid;gap:13px}.app-ranking>div{display:grid;gap:6px}.app-ranking__label{display:grid;grid-template-columns:20px minmax(0,1fr) auto;align-items:center;gap:7px}.app-ranking__label>b{color:#94a3b8;font-size:11px}.app-ranking__label strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.app-ranking__label small{color:var(--color-text-muted)}.app-ranking>div>i{height:5px;overflow:hidden;border-radius:3px;background:#e2e8f0}.app-ranking>div>i>b{display:block;height:100%}.daily-chart{display:flex;align-items:end;gap:7px;height:220px;overflow-x:auto;padding-top:16px}.daily-chart>div{display:grid;grid-template-rows:180px auto;min-width:30px;flex:1;gap:7px;text-align:center}.daily-bars{display:flex;align-items:end;justify-content:center;gap:3px}.daily-bars i{width:8px;min-height:2px;background:#16a34a}.daily-bars i+i{background:#2563eb}.daily-chart small{color:#64748b;font-size:9px}.session-drawer-backdrop{position:fixed;inset:0;z-index:80;background:rgb(15 23 42 / 35%)}.session-drawer{position:absolute;inset:0 0 0 auto;width:min(460px,100%);overflow:auto;padding:24px;background:#fff;box-shadow:-14px 0 30px rgb(15 23 42 / 18%)}.session-drawer header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding-bottom:18px;border-bottom:1px solid var(--border-color)}.session-drawer header p{margin-top:5px;color:var(--color-text-muted)}.session-drawer dl{display:grid;grid-template-columns:repeat(3,1fr);margin:18px 0;border:1px solid var(--border-color);border-radius:8px}.session-drawer dl div{padding:12px}.session-drawer dt{color:var(--color-text-muted);font-size:11px}.session-drawer dd{margin:5px 0 0;font-weight:700}.session-contexts{display:grid}.session-contexts article{display:flex;justify-content:space-between;gap:16px;padding:13px 0;border-bottom:1px solid var(--border-color)}.session-contexts strong,.session-contexts small{display:block}.session-contexts small{margin-top:4px;color:var(--color-text-muted);overflow-wrap:anywhere}@media(max-width:1050px){.computer-overview-grid{grid-template-columns:1fr}}@media(max-width:900px){.computer-parameter-grid{grid-template-columns:1fr}.computer-two-column{grid-template-columns:1fr}}@media(max-width:640px){.computer-toolbar{align-items:stretch;flex-direction:column}.computer-toolbar label{min-width:0}.segmented button{min-width:0;flex:1}.computer-status-hero{grid-template-columns:auto 1fr}.computer-status-hero>b{grid-column:1/-1;max-width:none}.computer-metrics{grid-template-columns:1fr 1fr}.computer-metrics strong{font-size:17px;white-space:nowrap}.session-list button{grid-template-columns:36px 1fr}.session-summary{grid-column:2;text-align:left}.session-drawer dl{grid-template-columns:1fr}}
</style>
