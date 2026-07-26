<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import DeviceManagementPanel from "@/components/device/DeviceManagementPanel.vue";
import DeviceMetricStrip, { type DeviceMetric } from "@/components/device/DeviceMetricStrip.vue";
import DevicePairPanel from "@/components/device/DevicePairPanel.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import { computerApi } from "@/api/computer";
import { deviceRegistryApi } from "@/api/deviceRegistry";
import type { ComputerRange, ComputerSession } from "@/types/computer";
import {
  dominantComputerState,
  durationLabel,
  mergeComputerTimeline,
  timelinePosition,
  timelineTicks,
  type ComputerTimelineSegment,
} from "@/utils/computer";
import { formatDateTime } from "@/utils/date";

const APP_COLORS = ["#2563eb", "#0891b2", "#db2777", "#d97706", "#16a34a", "#475569"];
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
const axisTicks = computed(() => report.value ? timelineTicks(report.value.windowStart, report.value.windowEnd, 6) : []);
const stateSegments = computed(() => mergeComputerTimeline(report.value?.timeline ?? [], (point) => {
  const state = dominantComputerState(point);
  return { key: state, label: stateLabel(state) };
}));
const appSegments = computed(() => mergeComputerTimeline(report.value?.timeline ?? [], (point) => {
  const context = point.dominantContext;
  return context ? { key: context.contextId || context.bundleId, label: context.appName } : null;
}));
const metrics = computed<DeviceMetric[]>(() => [
  { label: t("computer.activeTime"), value: duration(report.value?.totals.activeSeconds ?? 0), note: t("computer.selectedRange"), tone: "success" },
  { label: t("computer.plannedActive"), value: duration(report.value?.totals.plannedActiveSeconds ?? 0), note: t("computer.planOverlapNote") },
  { label: t("computer.idleTime"), value: duration(report.value?.totals.idleSeconds ?? 0), note: t("computer.objectiveOnly"), tone: "warning" },
  { label: t("computer.switches"), value: String(report.value?.totals.switchCount ?? 0), note: t("computer.applicationChanges"), tone: "neutral" },
]);

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
function duration(seconds: number) { return durationLabel(seconds, locale.value === "en-US" ? "en-US" : "zh-CN"); }
function currentDuration() {
  if (!monitor.value?.stateSince) return t("common.notSet");
  return duration((Date.now() - new Date(monitor.value.stateSince).getTime()) / 1000);
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
function appInitial(value?: string | null) { return (value?.trim().charAt(0) || "?").toUpperCase(); }
function segmentStyle(segment: ComputerTimelineSegment, color?: string) {
  return { ...intervalStyle(segment.startAt, segment.endAt), ...(color ? { background: color } : {}) };
}
function segmentTitle(segment: ComputerTimelineSegment) {
  return `${timeLabel(segment.startAt)}–${timeLabel(segment.endAt)} · ${segment.label}`;
}
function segmentIsWide(segment: ComputerTimelineSegment) {
  if (!report.value) return false;
  const width = new Date(report.value.windowEnd).getTime() - new Date(report.value.windowStart).getTime();
  return (new Date(segment.endAt).getTime() - new Date(segment.startAt).getTime()) / Math.max(1, width) >= 0.045;
}
</script>

<template>
  <div class="computer-panel">
    <template v-if="computers.length">
      <div class="computer-toolbar">
        <label><span>{{ t("computer.device") }}</span><select v-model="selectedDeviceId"><option v-for="item in computers" :key="item.deviceId" :value="item.deviceId">{{ item.deviceName }}</option></select></label>
        <div class="segmented" role="group" :aria-label="t('computer.range')"><button v-for="item in (['today', '7d', '30d'] as ComputerRange[])" :key="item" type="button" :class="{ active: range === item }" @click="range = item">{{ t(`computer.rangeOption.${item}`) }}</button></div>
      </div>

      <div v-if="monitor && (monitor.paused || monitor.state === 'offline' || monitor.queueDepth > 5 || !monitor.accessibilityGranted)" class="computer-alert" :class="`computer-alert--${monitor.state}`">
        {{ !monitor.accessibilityGranted ? t("computer.accessibilityMissing") : monitor.paused ? t("computer.paused") : monitor.state === "offline" ? t("computer.offline") : t("computer.syncDelayed", { count: monitor.queueDepth }) }}
      </div>

      <section v-if="monitor" class="computer-live-summary">
        <span class="computer-state-dot" :class="`computer-state-dot--${monitor.state}`" />
        <div class="computer-live-summary__state"><span>{{ t("computer.current") }}</span><strong>{{ stateLabel(monitor.state) }}</strong><small>{{ currentDuration() }} · {{ monitor.currentAppName || t("computer.noTitle") }}</small></div>
        <div class="computer-live-summary__context"><span>{{ t("computer.context") }}</span><strong>{{ monitor.currentWindowTitle || monitor.currentAppName || t("common.notSet") }}</strong><small>{{ t("computer.lastSync") }} · {{ formatDateTime(monitor.lastHeartbeatAt, locale === 'en-US' ? 'en-US' : 'zh-CN') }}</small></div>
        <div class="computer-live-summary__analysis"><span>{{ t("computer.analysis") }}</span><strong>{{ analysisLabel(monitor.analysis.state) }}</strong><small>{{ analysisBasis() }}</small></div>
      </section>
      <EmptyState v-else :text="t('computer.waitingHeartbeat')" />

      <DeviceMetricStrip :items="metrics" :label="t('computer.activitySummary')" />

      <BaseCard v-if="range === 'today'" :title="t('computer.activityMap')" :subtitle="t('computer.activityMapNote')">
        <div v-if="report?.timeline.length" class="computer-activity-map-scroll" tabindex="0">
          <div class="computer-activity-map">
            <div class="computer-map-legend"><span v-for="state in OBJECTIVE_STATES" :key="state"><i :class="`timeline-key timeline-key--${state}`" />{{ stateLabel(state) }}</span></div>
            <div class="computer-map-axis"><span v-for="tick in axisTicks" :key="tick">{{ timeLabel(tick) }}</span></div>
            <div class="computer-map-row computer-map-row--plans">
              <strong>{{ t("computer.plans") }}</strong>
              <div class="computer-map-track"><i v-for="plan in report.plans" :key="plan.evtId" class="computer-map-block computer-map-block--plan" :style="intervalStyle(plan.startAt, plan.endAt)" :title="`${plan.title} · ${duration(plan.activeSeconds)}`"><span>{{ plan.title }}</span></i><span v-if="!report.plans.length" class="timeline-empty">{{ t("computer.noPlans") }}</span></div>
            </div>
            <div class="computer-map-row">
              <strong>{{ t("computer.statusLane") }}</strong>
              <div class="computer-map-track"><i v-for="segment in stateSegments" :key="`${segment.startAt}-${segment.key}`" class="computer-map-block" :class="`computer-map-block--${segment.key}`" :style="segmentStyle(segment)" :title="segmentTitle(segment)"><span v-if="segmentIsWide(segment)">{{ segment.label }}</span></i></div>
            </div>
            <div class="computer-map-row">
              <strong>{{ t("computer.appLane") }}</strong>
              <div class="computer-map-track"><i v-for="segment in appSegments" :key="`${segment.startAt}-${segment.key}`" class="computer-map-block computer-map-block--app" :style="segmentStyle(segment, stableColor(segment.key))" :title="segmentTitle(segment)"><span v-if="segmentIsWide(segment)">{{ segment.label }}</span></i></div>
            </div>
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

      <DeviceManagementPanel icon="Mac" :title="t('computer.managementTitle')" :summary="t('computer.managementSummary', { count: computers.length })">
        <div v-if="monitor" class="computer-runtime-grid"><div><span>{{ t("computer.lastSync") }}</span><strong>{{ formatDateTime(monitor.lastHeartbeatAt, locale === 'en-US' ? 'en-US' : 'zh-CN') }}</strong></div><div><span>{{ t("computer.permission") }}</span><strong>{{ monitor.accessibilityGranted ? t("computer.granted") : t("computer.notGranted") }}</strong></div><div><span>{{ t("computer.queueLabel") }}</span><strong>{{ monitor.queueDepth }}</strong></div><div><span>{{ t("computer.version") }}</span><strong>{{ monitor.appVersion || t("common.notSet") }}</strong></div></div>
        <DevicePairPanel embedded :allowed-kinds="['computer']" :title="t('computer.pairTitle')" />
      </DeviceManagementPanel>
    </template>

    <template v-else>
      <EmptyState :text="t('computer.noDevice')" />
      <DeviceManagementPanel icon="Mac" :title="t('computer.managementTitle')" :summary="t('computer.managementSummary', { count: 0 })"><DevicePairPanel embedded :allowed-kinds="['computer']" :title="t('computer.pairTitle')" /></DeviceManagementPanel>
    </template>

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
.computer-panel{display:grid;grid-auto-rows:max-content;align-content:start;gap:18px}.computer-toolbar{display:flex;align-items:end;justify-content:space-between;gap:16px}.computer-toolbar label{display:grid;min-width:240px;gap:6px;color:var(--color-text-muted);font-size:12px}.computer-toolbar select{min-height:40px;padding:0 11px;border:1px solid var(--border-color);border-radius:7px;background:#fff;color:var(--color-text);font:inherit}.computer-alert{padding:12px 14px;border-left:4px solid #d97706;background:#fffbeb;color:#92400e}.computer-alert--offline,.computer-alert--paused{border-left-color:#64748b;background:#f8fafc;color:#475569}.computer-live-summary{display:grid;grid-template-columns:auto minmax(160px,.55fr) minmax(240px,1fr) minmax(220px,.85fr);align-items:center;gap:16px;padding:16px 18px;border:1px solid var(--border-color);border-radius:8px;background:#fff;box-shadow:var(--shadow-card)}.computer-live-summary>div{min-width:0}.computer-live-summary span,.computer-live-summary strong,.computer-live-summary small{display:block}.computer-live-summary>div>span,.computer-live-summary small{color:var(--color-text-muted);font-size:11px}.computer-live-summary strong{margin:5px 0;overflow:hidden;font-size:15px;text-overflow:ellipsis;white-space:nowrap}.computer-live-summary__state strong{font-size:21px}.computer-live-summary__context,.computer-live-summary__analysis{padding-left:16px;border-left:1px solid var(--border-color)}.computer-state-dot{width:20px;height:20px;border:5px solid #e2e8f0;border-radius:50%;background:#94a3b8;box-sizing:content-box}.computer-state-dot--active{border-color:#dcfce7;background:#16a34a}.computer-state-dot--idle{border-color:#fef3c7;background:#d97706}.computer-state-dot--locked,.computer-state-dot--sleeping{border-color:#e2e8f0;background:#475569}.computer-state-dot--paused{border-color:#dbeafe;background:#2563eb}.computer-activity-map-scroll{overflow-x:auto;overscroll-behavior-x:contain;padding:3px 0 8px}.computer-activity-map{min-width:760px}.computer-map-legend{display:flex;justify-content:flex-end;flex-wrap:wrap;gap:12px;margin-bottom:10px;color:#64748b;font-size:10px}.computer-map-legend span{display:flex;align-items:center;gap:5px}.timeline-key{width:8px;height:8px;border-radius:2px;background:#94a3b8}.timeline-key--active{background:#16a34a}.timeline-key--idle{background:#d97706}.timeline-key--locked{background:#64748b}.timeline-key--sleeping{background:#0f172a}.timeline-key--paused{background:#0ea5e9}.computer-map-axis{display:flex;justify-content:space-between;margin:0 4px 6px 114px;color:#94a3b8;font-size:10px}.computer-map-row{display:grid;grid-template-columns:104px minmax(0,1fr);align-items:center;gap:10px;margin-top:10px}.computer-map-row>strong{color:#475569;font-size:12px}.computer-map-track{position:relative;height:48px;overflow:hidden;border:1px solid var(--border-color);border-radius:6px;background:repeating-linear-gradient(90deg,#f8fafc 0,#f8fafc calc(20% - 1px),#e2e8f0 20%)}.computer-map-row--plans .computer-map-track{height:54px}.computer-map-block{position:absolute;top:7px;height:34px;min-width:3px;overflow:hidden;border-radius:4px;background:#94a3b8;color:#fff;font-style:normal}.computer-map-block>span{display:block;overflow:hidden;padding:9px 8px;font-size:10px;font-weight:700;text-overflow:ellipsis;white-space:nowrap}.computer-map-block--plan{top:7px;height:40px;background:#2563eb}.computer-map-block--plan>span{padding-top:11px}.computer-map-block--active{background:#16a34a}.computer-map-block--idle{background:#d97706}.computer-map-block--locked{background:#64748b}.computer-map-block--sleeping{background:#0f172a}.computer-map-block--paused{background:#0ea5e9}.computer-map-block--app{background:#0891b2}.timeline-empty{position:absolute;inset:0;display:grid;place-items:center;color:#94a3b8;font-size:10px}.computer-two-column{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(320px,.75fr);gap:18px}.session-list{display:grid;gap:7px}.session-list button{display:grid;grid-template-columns:36px minmax(0,1fr) auto;align-items:center;gap:11px;width:100%;padding:10px;border:1px solid #eef2f7;border-radius:7px;background:#fff;text-align:left}.session-list button:hover{border-color:#bfdbfe;background:#f8fbff}.session-app-mark{display:grid;width:34px;height:34px;place-items:center;border-radius:7px;color:#fff;font-size:13px;font-style:normal;font-weight:800}.session-main strong,.session-main small,.session-summary strong,.session-summary small{display:block}.session-main strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.session-main small,.session-summary small{margin-top:3px;color:var(--color-text-muted);font-size:10px}.session-summary{text-align:right}.app-ranking{display:grid;gap:13px}.app-ranking>div{display:grid;gap:6px}.app-ranking__label{display:grid;grid-template-columns:20px minmax(0,1fr) auto;align-items:center;gap:7px}.app-ranking__label>b{color:#94a3b8;font-size:11px}.app-ranking__label strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.app-ranking__label small{color:var(--color-text-muted)}.app-ranking>div>i{height:5px;overflow:hidden;border-radius:3px;background:#e2e8f0}.app-ranking>div>i>b{display:block;height:100%}.daily-chart{display:flex;align-items:end;gap:7px;height:220px;overflow-x:auto;padding-top:16px}.daily-chart>div{display:grid;grid-template-rows:180px auto;min-width:30px;flex:1;gap:7px;text-align:center}.daily-bars{display:flex;align-items:end;justify-content:center;gap:3px}.daily-bars i{width:8px;min-height:2px;background:#16a34a}.daily-bars i+i{background:#2563eb}.daily-chart small{color:#64748b;font-size:9px}.computer-runtime-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin-bottom:18px}.computer-runtime-grid>div{min-width:0;padding:12px;border-radius:7px;background:#f8fafc}.computer-runtime-grid span,.computer-runtime-grid strong{display:block}.computer-runtime-grid span{color:var(--color-text-muted);font-size:10px}.computer-runtime-grid strong{margin-top:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.session-drawer-backdrop{position:fixed;inset:0;z-index:80;background:rgb(15 23 42 / 35%)}.session-drawer{position:absolute;inset:0 0 0 auto;width:min(460px,100%);overflow:auto;padding:24px;background:#fff;box-shadow:-14px 0 30px rgb(15 23 42 / 18%)}.session-drawer header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding-bottom:18px;border-bottom:1px solid var(--border-color)}.session-drawer header p{margin-top:5px;color:var(--color-text-muted)}.session-drawer dl{display:grid;grid-template-columns:repeat(3,1fr);margin:18px 0;border:1px solid var(--border-color);border-radius:8px}.session-drawer dl div{padding:12px}.session-drawer dt{color:var(--color-text-muted);font-size:11px}.session-drawer dd{margin:5px 0 0;font-weight:700}.session-contexts{display:grid}.session-contexts article{display:flex;justify-content:space-between;gap:16px;padding:13px 0;border-bottom:1px solid var(--border-color)}.session-contexts strong,.session-contexts small{display:block}.session-contexts small{margin-top:4px;color:var(--color-text-muted);overflow-wrap:anywhere}@media(max-width:1050px){.computer-live-summary{grid-template-columns:auto minmax(0,1fr) minmax(0,1fr)}.computer-live-summary__analysis{grid-column:2/-1}.computer-two-column{grid-template-columns:1fr}}@media(max-width:760px){.computer-toolbar{align-items:stretch;flex-direction:column}.computer-toolbar label{min-width:0}.segmented button{min-width:0;flex:1}.computer-live-summary{grid-template-columns:auto minmax(0,1fr)}.computer-live-summary__context,.computer-live-summary__analysis{grid-column:1/-1;padding:12px 0 0;border-top:1px solid var(--border-color);border-left:0}.computer-runtime-grid{grid-template-columns:1fr 1fr}.session-list button{grid-template-columns:36px 1fr}.session-summary{grid-column:2;text-align:left}.session-drawer dl{grid-template-columns:1fr}}
</style>
