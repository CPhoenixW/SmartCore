<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import DeviceManagementPanel from "@/components/device/DeviceManagementPanel.vue";
import DeviceMetricStrip, { type DeviceMetric } from "@/components/device/DeviceMetricStrip.vue";
import DevicePairPanel from "@/components/device/DevicePairPanel.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import BarChart, { type BarChartSeries } from "@/components/base/BarChart.vue";
import { computerApi } from "@/api/computer";
import { deviceRegistryApi } from "@/api/deviceRegistry";
import type { ComputerPlanAssessment, ComputerProjectInvestment, ComputerRange, ComputerSession, ComputerWorkBlock } from "@/types/computer";
import {
  dominantComputerState,
  durationLabel,
  mergeComputerTimeline,
  timelinePosition,
  timelineTicks,
  type ComputerTimelineSegment,
} from "@/utils/computer";
import { formatDateTime, todayKey } from "@/utils/date";
import { scrollToLatest } from "@/utils/scroll";

const APP_COLORS = ["#2563eb", "#0891b2", "#db2777", "#d97706", "#16a34a", "#475569"];
const OBJECTIVE_STATES = ["active", "idle", "locked", "sleeping", "paused"] as const;

const { t, locale } = useI18n();
const range = ref<ComputerRange>("today");
const selectedDeviceId = ref("");
const selectedDate = ref(todayKey());
const selectedSession = ref<ComputerSession | null>(null);
const showHourlyEvidence = ref(false);
const activityMapScroll = ref<HTMLElement | null>(null);
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
const activityMapUsage = useQuery({
  queryKey: ["computer", "usage", selectedDeviceId, "24h", timezone],
  queryFn: () => computerApi.usage(selectedDeviceId.value, "24h", timezone),
  enabled: computed(() => enabled.value && range.value === "today"),
  refetchInterval: 60_000,
});
const insights = useQuery({
  queryKey: ["computer", "insights", selectedDeviceId, selectedDate],
  queryFn: () => computerApi.insights(selectedDeviceId.value, selectedDate.value),
  enabled,
  refetchInterval: 60_000,
});
const report = computed(() => usage.data.value);
const mapReport = computed(() => activityMapUsage.data.value ?? report.value);
const monitor = computed(() => status.data.value ?? report.value?.status ?? null);
const recentWorkBlocks = computed(() =>
  [...(insights.data.value?.workBlocks ?? [])]
    .filter((block) => block.status === "closed")
    .reverse(),
);
const maxProjectActive = computed(() => Math.max(1, ...(insights.data.value?.projects ?? []).map((item) => item.activeSeconds)));
const maxApp = computed(() => Math.max(1, ...(report.value?.applications ?? []).map((item) => item.seconds)));
const dailyLabels = computed(() => (report.value?.daily ?? []).map((item) => item.date.slice(5)));
const dailySeries = computed<BarChartSeries[]>(() => [
  {
    key: "active",
    name: t("computer.activeTime"),
    color: "#16a34a",
    values: (report.value?.daily ?? []).map((item) => item.activeSeconds),
    displayValues: (report.value?.daily ?? []).map((item) => duration(item.activeSeconds)),
  },
  {
    key: "planned",
    name: t("computer.plannedActive"),
    color: "#2563eb",
    values: (report.value?.daily ?? []).map((item) => item.plannedActiveSeconds),
    displayValues: (report.value?.daily ?? []).map((item) => duration(item.plannedActiveSeconds)),
  },
]);
const axisTicks = computed(() => mapReport.value ? timelineTicks(mapReport.value.windowStart, mapReport.value.windowEnd, 7) : []);
const stateSegments = computed(() => mergeComputerTimeline(mapReport.value?.timeline ?? [], (point) => {
  const state = dominantComputerState(point);
  return { key: state, label: stateLabel(state) };
}));
const appSegments = computed(() => mergeComputerTimeline(mapReport.value?.timeline ?? [], (point) => {
  const context = point.dominantContext;
  return context ? { key: context.contextId || context.bundleId, label: context.appName } : null;
}));
const metrics = computed<DeviceMetric[]>(() => [
  { label: t("computer.activeTime"), value: duration(report.value?.totals.activeSeconds ?? 0), note: monitor.value ? `${t("computer.current")}: ${stateLabel(monitor.value.state)}` : t("computer.waitingHeartbeat"), tone: monitor.value?.state === "active" ? "success" : "neutral" },
  { label: t("computer.plannedActive"), value: duration(report.value?.totals.plannedActiveSeconds ?? 0), note: t("computer.planOverlapNote") },
  { label: t("computer.idleTime"), value: duration(report.value?.totals.idleSeconds ?? 0), note: t("computer.objectiveOnly"), tone: "warning" },
  { label: t("computer.switches"), value: String(report.value?.totals.switchCount ?? 0), note: t("computer.applicationChanges"), tone: "neutral" },
]);

watch([range, () => mapReport.value?.windowEnd], async ([selectedRange, windowEnd]) => {
  if (selectedRange !== "today" || !windowEnd) return;
  await nextTick();
  scrollToLatest(activityMapScroll.value);
});
function stateLabel(state: string) { return t(`computer.state.${state}`); }
function timeLabel(value: string) {
  return new Date(value).toLocaleTimeString(locale.value === "en-US" ? "en-US" : "zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
}
function duration(seconds: number) { return durationLabel(seconds, locale.value === "en-US" ? "en-US" : "zh-CN"); }
function intervalStyle(startAt: string, endAt: string) {
  if (!mapReport.value) return {};
  return timelinePosition(startAt, endAt, mapReport.value.windowStart, mapReport.value.windowEnd);
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
  if (!mapReport.value) return false;
  const width = new Date(mapReport.value.windowEnd).getTime() - new Date(mapReport.value.windowStart).getTime();
  return (new Date(segment.endAt).getTime() - new Date(segment.startAt).getTime()) / Math.max(1, width) >= 0.045;
}
function planStateLabel(item: ComputerPlanAssessment) { return t(`computer.planExecutionState.${item.state}`); }
function insightStatusLabel(statusValue: string) { return t(`computer.insightStatus.${statusValue}`); }
function blockEndLabel(block: ComputerWorkBlock) {
  return block.endAt ? timeLabel(block.endAt) : t("computer.ongoing");
}
function semanticLabel(value?: string) { return t(`computer.semanticAlignment.${value || "unclear"}`); }
function codexStatusLabel(value: string) { return t(`computer.codexStatus.${value}`); }
function projectStatusLabel(project: ComputerProjectInvestment) {
  return project.status ? codexStatusLabel(project.status) : t("computer.observedOnly");
}
</script>

<template>
  <div class="computer-panel">
    <template v-if="computers.length">
      <div class="computer-toolbar">
        <div class="computer-toolbar__fields">
          <label><span>{{ t("computer.device") }}</span><select v-model="selectedDeviceId"><option v-for="item in computers" :key="item.deviceId" :value="item.deviceId">{{ item.deviceName }}</option></select></label>
          <label><span>{{ t("computer.insightDate") }}</span><input v-model="selectedDate" type="date" :max="todayKey()" /></label>
        </div>
        <div class="segmented" role="group" :aria-label="t('computer.range')"><button v-for="item in (['today', '7d', '30d'] as ComputerRange[])" :key="item" type="button" :class="{ active: range === item }" @click="range = item">{{ t(`computer.rangeOption.${item}`) }}</button></div>
      </div>

      <div v-if="monitor && (monitor.paused || monitor.state === 'offline' || monitor.queueDepth > 5 || !monitor.accessibilityGranted)" class="computer-alert" :class="`computer-alert--${monitor.state}`">
        {{ !monitor.accessibilityGranted ? t("computer.accessibilityMissing") : monitor.paused ? t("computer.paused") : monitor.state === "offline" ? t("computer.offline") : t("computer.syncDelayed", { count: monitor.queueDepth }) }}
      </div>

      <DeviceMetricStrip :items="metrics" :label="t('computer.activitySummary')" />

      <section v-if="range === 'today'" class="computer-insights-grid">
        <BaseCard class="computer-work-block-primary" :title="t('computer.currentWorkBlock')">
          <template v-if="insights.data.value?.currentBlock">
          <article class="computer-work-block computer-work-block--current">
            <header><div><span class="computer-work-block__status">{{ t('computer.ongoing') }}</span><strong>{{ insights.data.value.currentBlock.title || t('computer.analysisPending') }}</strong></div><time>{{ timeLabel(insights.data.value.currentBlock.startAt) }}–{{ blockEndLabel(insights.data.value.currentBlock) }}</time></header>
            <p v-if="insights.data.value.currentBlock.summary">{{ insights.data.value.currentBlock.summary }}</p>
            <div class="computer-work-block__metrics"><span>{{ t('computer.activeTime') }} <b>{{ duration(insights.data.value.currentBlock.activeSeconds) }}</b></span><span>{{ t('computer.plannedActive') }} <b>{{ duration(insights.data.value.currentBlock.plannedActiveSeconds) }}</b></span><span v-if="insights.data.value.currentBlock.primaryApps.length">{{ insights.data.value.currentBlock.primaryApps.map((item) => item.appName).slice(0, 3).join(t('common.listSeparator')) }}</span></div>
            <dl v-if="insights.data.value.currentBlock.progress || insights.data.value.currentBlock.outcome || insights.data.value.currentBlock.blocker || insights.data.value.currentBlock.nextStep" class="computer-work-block__details"><div v-if="insights.data.value.currentBlock.progress"><dt>{{ t('computer.progress') }}</dt><dd>{{ insights.data.value.currentBlock.progress }}</dd></div><div v-if="insights.data.value.currentBlock.outcome"><dt>{{ t('computer.outcome') }}</dt><dd>{{ insights.data.value.currentBlock.outcome }}</dd></div><div v-if="insights.data.value.currentBlock.blocker"><dt>{{ t('computer.blocker') }}</dt><dd>{{ insights.data.value.currentBlock.blocker }}</dd></div><div v-if="insights.data.value.currentBlock.nextStep"><dt>{{ t('computer.nextStep') }}</dt><dd>{{ insights.data.value.currentBlock.nextStep }}</dd></div></dl>
          </article>
          <div v-if="insights.data.value.analysisState && insights.data.value.analysisState.status !== 'complete'" class="computer-analysis-state"><strong>{{ insightStatusLabel(insights.data.value.analysisState.status) }}</strong><p v-if="insights.data.value.analysisState.errorMessage">{{ insights.data.value.analysisState.errorMessage }}</p><small v-if="insights.data.value.analysisState.nextRetryAt">{{ formatDateTime(insights.data.value.analysisState.nextRetryAt, locale === 'en-US' ? 'en-US' : 'zh-CN') }}</small></div>
          </template>
          <div v-else-if="insights.data.value?.analysisState && ['queued', 'running', 'failed'].includes(insights.data.value.analysisState.status)" class="computer-analysis-state"><strong>{{ insightStatusLabel(insights.data.value.analysisState.status) }}</strong><p v-if="insights.data.value.analysisState.errorMessage">{{ insights.data.value.analysisState.errorMessage }}</p><small v-if="insights.data.value.analysisState.nextRetryAt">{{ formatDateTime(insights.data.value.analysisState.nextRetryAt, locale === 'en-US' ? 'en-US' : 'zh-CN') }}</small></div>
          <EmptyState v-else :text="t('computer.noCurrentWorkBlock')" />
        </BaseCard>
        <BaseCard class="computer-project-investment-card" :title="t('computer.projectInvestment')" :subtitle="t('computer.projectInvestmentNote')">
          <div v-if="insights.data.value?.projects?.length" class="computer-project-list">
            <article v-for="project in insights.data.value?.projects ?? []" :key="project.projectKey" class="computer-project">
              <header>
                <div>
                  <strong>{{ project.projectName }}</strong>
                  <span>{{ projectStatusLabel(project) }}</span>
                </div>
                <b>{{ duration(project.activeSeconds) }}</b>
              </header>
              <div class="computer-project__bar" aria-hidden="true"><i :style="{ width: `${project.activeSeconds / maxProjectActive * 100}%` }" /></div>
              <div class="computer-project__meta">
                <span v-if="project.statusCounts.completed">{{ t('computer.codexStatusCount.completed', { count: project.statusCounts.completed }) }}</span>
                <span v-if="project.statusCounts.partial">{{ t('computer.codexStatusCount.partial', { count: project.statusCounts.partial }) }}</span>
                <span v-if="project.statusCounts.inProgress">{{ t('computer.codexStatusCount.in_progress', { count: project.statusCounts.inProgress }) }}</span>
                <span v-if="project.workBlocks.length">{{ t('computer.blockEvidenceCount', { count: project.workBlocks.length }) }}</span>
                <span v-if="project.plans.length">{{ t('computer.planCount', { count: project.plans.length }) }}</span>
              </div>
              <div v-if="project.codexReports.length" class="computer-project__reports">
                <article v-for="reportItem in project.codexReports" :key="reportItem.reportId">
                  <div><strong>{{ reportItem.title }}</strong><span :class="`computer-codex-status computer-codex-status--${reportItem.status}`">{{ codexStatusLabel(reportItem.status) }}</span></div>
                  <p>{{ reportItem.summary }}</p>
                </article>
              </div>
            </article>
          </div>
          <EmptyState v-else :text="t('computer.noProjectInvestment')" />
        </BaseCard>
        <BaseCard :title="t('computer.recentWorkBlocks')">
          <div v-if="recentWorkBlocks.length" class="computer-work-block-list computer-card-scroll">
            <article v-for="block in recentWorkBlocks" :key="block.blockId" class="computer-work-block">
              <header><div><strong>{{ block.title || t('computer.analysisPending') }}</strong><small>{{ duration(block.activeSeconds) }}</small></div><time>{{ timeLabel(block.startAt) }}–{{ blockEndLabel(block) }}</time></header>
              <p v-if="block.summary">{{ block.summary }}</p>
              <div class="computer-work-block__metrics"><span v-if="block.primaryApps.length">{{ block.primaryApps.map((item) => item.appName).slice(0, 3).join(t('common.listSeparator')) }}</span><span v-if="block.planAssessments.length">{{ t('computer.planCount', { count: block.planAssessments.length }) }}</span></div>
            </article>
          </div>
          <EmptyState v-else :text="t('computer.noWorkBlocks')" />
          <button v-if="insights.data.value?.legacyHours.length" class="button button--ghost computer-evidence-button" type="button" @click="showHourlyEvidence = true">{{ t('computer.viewHourlyEvidence') }}</button>
        </BaseCard>
        <BaseCard :title="t('computer.planExecution')">
          <div v-if="insights.data.value?.planAssessments.length" class="computer-plan-assessments computer-card-scroll">
            <article v-for="(item, index) in insights.data.value.planAssessments" :key="`${item.evtId}-${index}`">
              <div><strong>{{ planStateLabel(item) }}</strong><span>{{ t(`computer.confidence.${item.confidence}`) }}</span></div>
              <p>{{ item.title || item.note || item.evidenceCodes.join(t('common.listSeparator')) }}</p>
              <small v-if="item.overlapRatio !== undefined">{{ t('computer.objectiveOverlap', { percent: Math.round(item.overlapRatio * 100) }) }}</small>
              <small v-if="item.semanticAlignment"> · {{ semanticLabel(item.semanticAlignment) }}</small>
            </article>
          </div>
          <EmptyState v-else :text="t('computer.noPlanAssessment')" />
        </BaseCard>
        <BaseCard :title="t('computer.workTopics')">
          <div v-if="insights.data.value?.topics.length" class="computer-topic-list">
            <article v-for="topic in insights.data.value.topics" :key="topic.name"><div><strong>{{ topic.name }}</strong><small>{{ duration(topic.activeSeconds) }} · {{ t('computer.blockEvidenceCount', { count: (topic.blockIds ?? []).length }) }}</small></div><p v-if="topic.summary">{{ topic.summary }}</p></article>
          </div>
          <EmptyState v-else :text="t('computer.noTopics')" />
        </BaseCard>
        <BaseCard :title="t('computer.dailyWorkLog')">
          <article v-if="insights.data.value?.dailyLog" class="computer-daily-log">
            <div><strong>{{ insights.data.value.dailyLog.title || insightStatusLabel(insights.data.value.dailyLog.status) }}</strong><span>{{ t(`computer.dailyLogPhase.${insights.data.value.dailyLog.phase}`) }} · {{ insightStatusLabel(insights.data.value.dailyLog.status) }}</span></div>
            <p>{{ insights.data.value.dailyLog.summary || insights.data.value.dailyLog.errorMessage || t('computer.analysisPending') }}</p>
            <small>{{ t('computer.smartReminderCount', { count: insights.data.value.reminders.length }) }}</small>
          </article>
          <EmptyState v-else :text="t('computer.noDailyLog')" />
        </BaseCard>
        <BaseCard :title="t('computer.smartReminders')">
          <div v-if="insights.data.value?.reminders.length" class="computer-reminder-list">
            <article v-for="(reminder, index) in insights.data.value.reminders" :key="`${reminder.dedupKey || reminder.title}-${index}`">
              <div><strong>{{ reminder.title }}</strong><span :class="`insight-state insight-state--${reminder.stat}`">{{ reminder.stat }}</span></div>
              <p>{{ reminder.content }}</p>
            </article>
          </div>
          <EmptyState v-else :text="t('computer.noSmartReminders')" />
        </BaseCard>
      </section>

      <BaseCard v-if="range === 'today'" :title="t('computer.activityMap')" :subtitle="t('computer.activityMapNote')">
        <div v-if="mapReport?.timeline.length" class="computer-activity-map-frame">
          <div class="computer-map-index" aria-hidden="true">
            <div class="computer-map-index__spacer" />
            <strong>{{ t("computer.plans") }}</strong>
            <strong>{{ t("computer.statusLane") }}</strong>
            <strong>{{ t("computer.appLane") }}</strong>
          </div>
          <div ref="activityMapScroll" class="computer-activity-map-scroll" tabindex="0">
            <div class="computer-activity-map">
              <div class="computer-map-legend"><span v-for="state in OBJECTIVE_STATES" :key="state"><i :class="`timeline-key timeline-key--${state}`" />{{ stateLabel(state) }}</span></div>
              <div class="computer-map-axis"><span v-for="tick in axisTicks" :key="tick">{{ timeLabel(tick) }}</span></div>
              <div class="computer-map-row computer-map-row--plans">
                <div class="computer-map-track"><i v-for="plan in mapReport.plans" :key="plan.evtId" class="computer-map-block computer-map-block--plan" :style="intervalStyle(plan.startAt, plan.endAt)" :title="`${plan.title} · ${duration(plan.activeSeconds)}`"><span>{{ plan.title }}</span></i><span v-if="!mapReport.plans.length" class="timeline-empty">{{ t("computer.noPlans") }}</span></div>
              </div>
              <div class="computer-map-row">
                <div class="computer-map-track"><i v-for="segment in stateSegments" :key="`${segment.startAt}-${segment.key}`" class="computer-map-block" :class="`computer-map-block--${segment.key}`" :style="segmentStyle(segment)" :title="segmentTitle(segment)"><span v-if="segmentIsWide(segment)">{{ segment.label }}</span></i></div>
              </div>
              <div class="computer-map-row">
                <div class="computer-map-track"><i v-for="segment in appSegments" :key="`${segment.startAt}-${segment.key}`" class="computer-map-block computer-map-block--app" :style="segmentStyle(segment, stableColor(segment.key))" :title="segmentTitle(segment)"><span v-if="segmentIsWide(segment)">{{ segment.label }}</span></i></div>
              </div>
            </div>
          </div>
        </div>
        <EmptyState v-else :text="t('computer.noUsage')" />
      </BaseCard>

      <div v-if="range === 'today'" class="computer-two-column computer-two-column--scroll">
        <BaseCard :title="t('computer.sessions')">
          <div v-if="report?.sessions.length" class="session-list computer-card-scroll">
            <button v-for="session in report.sessions" :key="session.sessionId" type="button" @click="selectedSession = session">
              <i class="session-app-mark" :style="{ background: stableColor(session.contexts[0]?.bundleId || session.sessionId) }">{{ appInitial(session.contexts[0]?.appName) }}</i>
              <span class="session-main"><strong>{{ session.contexts[0]?.appName || t("common.notSet") }}</strong><small>{{ timeLabel(session.startAt) }}–{{ timeLabel(session.endAt) }}</small></span>
              <span class="session-summary"><strong>{{ duration(session.activeSeconds) }}</strong><small>{{ t("computer.sessionMeta", { switches: session.switchCount, planned: duration(session.plannedActiveSeconds) }) }}</small></span>
            </button>
          </div>
          <EmptyState v-else :text="t('computer.noSessions')" />
        </BaseCard>
        <BaseCard :title="t('computer.applications')">
          <div v-if="report?.applications.length" class="app-ranking computer-card-scroll"><div v-for="(app, index) in report.applications" :key="app.bundleId"><span class="app-ranking__label"><b>{{ index + 1 }}</b><strong>{{ app.appName }}</strong><small>{{ duration(app.seconds) }}</small></span><i><b :style="{ width: `${app.seconds / maxApp * 100}%`, background: stableColor(app.bundleId) }" /></i></div></div>
          <EmptyState v-else :text="t('computer.noUsage')" />
        </BaseCard>
      </div>

      <div v-else class="computer-two-column">
        <BaseCard :title="t('computer.dailyTrend')">
          <BarChart v-if="report?.daily.length" :labels="dailyLabels" :series="dailySeries" :label="t('computer.dailyTrend')" />
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
    <div v-if="showHourlyEvidence" class="session-drawer-backdrop" @click.self="showHourlyEvidence = false">
      <aside class="session-drawer" role="dialog" aria-modal="true" :aria-label="t('computer.hourlyEvidence')">
        <header><div><h2>{{ t('computer.hourlyEvidence') }}</h2><p>{{ selectedDate }}</p></div><button class="icon-button" type="button" :aria-label="t('common.close')" @click="showHourlyEvidence = false">×</button></header>
        <div class="computer-insight-list"><article v-for="hour in [...(insights.data.value?.legacyHours ?? [])].reverse()" :key="hour.analysisId"><header><time>{{ timeLabel(hour.hourStart) }}–{{ timeLabel(hour.hourEnd) }}</time><span :class="`insight-state insight-state--${hour.status}`">{{ insightStatusLabel(hour.status) }}</span></header><strong v-if="hour.title">{{ hour.title }}</strong><p v-if="hour.summary || hour.errorMessage">{{ hour.summary || hour.errorMessage }}</p><small>{{ t('computer.hourEvidence', { active: duration(hour.activeSeconds), planned: duration(hour.plannedActiveSeconds) }) }}</small></article></div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.computer-panel{display:grid;grid-auto-rows:max-content;align-content:start;gap:18px}.computer-toolbar{display:flex;align-items:end;justify-content:space-between;gap:16px}.computer-toolbar label{display:grid;min-width:240px;gap:6px;color:var(--color-text-muted);font-size:12px}.computer-toolbar select{min-height:40px;padding:0 11px;border:1px solid var(--border-color);border-radius:7px;background:#fff;color:var(--color-text);font:inherit}.computer-alert{padding:12px 14px;border-left:4px solid #d97706;background:#fffbeb;color:#92400e}.computer-alert--offline,.computer-alert--paused{border-left-color:#64748b;background:#f8fafc;color:#475569}.computer-live-summary{display:grid;grid-template-columns:auto minmax(160px,.55fr) minmax(240px,1fr) minmax(220px,.85fr);align-items:center;gap:16px;padding:16px 18px;border:1px solid var(--border-color);border-radius:8px;background:#fff;box-shadow:var(--shadow-card)}.computer-live-summary>div{min-width:0}.computer-live-summary span,.computer-live-summary strong,.computer-live-summary small{display:block}.computer-live-summary>div>span,.computer-live-summary small{color:var(--color-text-muted);font-size:11px}.computer-live-summary strong{margin:5px 0;overflow:hidden;font-size:15px;text-overflow:ellipsis;white-space:nowrap}.computer-live-summary__state strong{font-size:21px}.computer-live-summary__context,.computer-live-summary__analysis{padding-left:16px;border-left:1px solid var(--border-color)}.computer-state-dot{width:20px;height:20px;border:5px solid #e2e8f0;border-radius:50%;background:#94a3b8;box-sizing:content-box}.computer-state-dot--active{border-color:#dcfce7;background:#16a34a}.computer-state-dot--idle{border-color:#fef3c7;background:#d97706}.computer-state-dot--locked,.computer-state-dot--sleeping{border-color:#e2e8f0;background:#475569}.computer-state-dot--paused{border-color:#dbeafe;background:#2563eb}.computer-activity-map-scroll{overflow-x:auto;overscroll-behavior-x:contain;padding:3px 0 8px}.computer-activity-map{min-width:760px}.computer-map-legend{display:flex;justify-content:flex-end;flex-wrap:wrap;gap:12px;margin-bottom:10px;color:#64748b;font-size:10px}.computer-map-legend span{display:flex;align-items:center;gap:5px}.timeline-key{width:8px;height:8px;border-radius:2px;background:#94a3b8}.timeline-key--active{background:#16a34a}.timeline-key--idle{background:#d97706}.timeline-key--locked{background:#64748b}.timeline-key--sleeping{background:#0f172a}.timeline-key--paused{background:#0ea5e9}.computer-map-axis{display:flex;justify-content:space-between;margin:0 4px 6px 114px;color:#94a3b8;font-size:10px}.computer-map-row{display:grid;grid-template-columns:104px minmax(0,1fr);align-items:center;gap:10px;margin-top:10px}.computer-map-row>strong{color:#475569;font-size:12px}.computer-map-track{position:relative;height:48px;overflow:hidden;border:1px solid var(--border-color);border-radius:6px;background:repeating-linear-gradient(90deg,#f8fafc 0,#f8fafc calc(20% - 1px),#e2e8f0 20%)}.computer-map-row--plans .computer-map-track{height:54px}.computer-map-block{position:absolute;top:7px;height:34px;min-width:3px;overflow:hidden;border-radius:4px;background:#94a3b8;color:#fff;font-style:normal}.computer-map-block>span{display:block;overflow:hidden;padding:9px 8px;font-size:10px;font-weight:700;text-overflow:ellipsis;white-space:nowrap}.computer-map-block--plan{top:7px;height:40px;background:#2563eb}.computer-map-block--plan>span{padding-top:11px}.computer-map-block--active{background:#16a34a}.computer-map-block--idle{background:#d97706}.computer-map-block--locked{background:#64748b}.computer-map-block--sleeping{background:#0f172a}.computer-map-block--paused{background:#0ea5e9}.computer-map-block--app{background:#0891b2}.timeline-empty{position:absolute;inset:0;display:grid;place-items:center;color:#94a3b8;font-size:10px}.computer-two-column{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(320px,.75fr);gap:18px}.session-list{display:grid;gap:7px}.session-list button{display:grid;grid-template-columns:36px minmax(0,1fr) auto;align-items:center;gap:11px;width:100%;padding:10px;border:1px solid #eef2f7;border-radius:7px;background:#fff;text-align:left}.session-list button:hover{border-color:#bfdbfe;background:#f8fbff}.session-app-mark{display:grid;width:34px;height:34px;place-items:center;border-radius:7px;color:#fff;font-size:13px;font-style:normal;font-weight:800}.session-main strong,.session-main small,.session-summary strong,.session-summary small{display:block}.session-main strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.session-main small,.session-summary small{margin-top:3px;color:var(--color-text-muted);font-size:10px}.session-summary{text-align:right}.app-ranking{display:grid;gap:13px}.app-ranking>div{display:grid;gap:6px}.app-ranking__label{display:grid;grid-template-columns:20px minmax(0,1fr) auto;align-items:center;gap:7px}.app-ranking__label>b{color:#94a3b8;font-size:11px}.app-ranking__label strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.app-ranking__label small{color:var(--color-text-muted)}.app-ranking>div>i{height:5px;overflow:hidden;border-radius:3px;background:#e2e8f0}.app-ranking>div>i>b{display:block;height:100%}.daily-chart{display:flex;align-items:end;gap:7px;height:220px;overflow-x:auto;padding-top:16px}.daily-chart>div{display:grid;grid-template-rows:180px auto;min-width:30px;flex:1;gap:7px;text-align:center}.daily-bars{display:flex;align-items:end;justify-content:center;gap:3px}.daily-bars i{width:8px;min-height:2px;background:#16a34a}.daily-bars i+i{background:#2563eb}.daily-chart small{color:#64748b;font-size:9px}.computer-runtime-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin-bottom:18px}.computer-runtime-grid>div{min-width:0;padding:12px;border-radius:7px;background:#f8fafc}.computer-runtime-grid span,.computer-runtime-grid strong{display:block}.computer-runtime-grid span{color:var(--color-text-muted);font-size:10px}.computer-runtime-grid strong{margin-top:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.session-drawer-backdrop{position:fixed;inset:0;z-index:80;background:rgb(15 23 42 / 35%)}.session-drawer{position:absolute;inset:0 0 0 auto;width:min(460px,100%);overflow:auto;padding:24px;background:#fff;box-shadow:-14px 0 30px rgb(15 23 42 / 18%)}.session-drawer header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding-bottom:18px;border-bottom:1px solid var(--border-color)}.session-drawer header p{margin-top:5px;color:var(--color-text-muted)}.session-drawer dl{display:grid;grid-template-columns:repeat(3,1fr);margin:18px 0;border:1px solid var(--border-color);border-radius:8px}.session-drawer dl div{padding:12px}.session-drawer dt{color:var(--color-text-muted);font-size:11px}.session-drawer dd{margin:5px 0 0;font-weight:700}.session-contexts{display:grid}.session-contexts article{display:flex;justify-content:space-between;gap:16px;padding:13px 0;border-bottom:1px solid var(--border-color)}.session-contexts strong,.session-contexts small{display:block}.session-contexts small{margin-top:4px;color:var(--color-text-muted);overflow-wrap:anywhere}@media(max-width:1050px){.computer-live-summary{grid-template-columns:auto minmax(0,1fr) minmax(0,1fr)}.computer-live-summary__analysis{grid-column:2/-1}.computer-two-column{grid-template-columns:1fr}}@media(max-width:760px){.computer-toolbar{align-items:stretch;flex-direction:column}.computer-toolbar label{min-width:0}.segmented button{min-width:0;flex:1}.computer-live-summary{grid-template-columns:auto minmax(0,1fr)}.computer-live-summary__context,.computer-live-summary__analysis{grid-column:1/-1;padding:12px 0 0;border-top:1px solid var(--border-color);border-left:0}.computer-runtime-grid{grid-template-columns:1fr 1fr}.session-list button{grid-template-columns:36px 1fr}.session-summary{grid-column:2;text-align:left}.session-drawer dl{grid-template-columns:1fr}}
.computer-toolbar__fields{display:flex;gap:12px}.computer-toolbar input{min-height:40px;padding:0 11px;border:1px solid var(--border-color);border-radius:7px;background:#fff;color:var(--color-text);font:inherit}.computer-plan-assessments small{color:var(--color-text-muted);font-size:10px}
</style>

<style scoped>
.computer-insights-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.computer-work-block-primary { grid-column: 1 / -1; }
.computer-project-investment-card { grid-column: 1 / -1; }
.computer-project-list { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 12px; }
.computer-project { min-width: 0; padding: 15px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; }
.computer-project > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.computer-project > header strong,.computer-project > header span { display: block; }
.computer-project > header strong { color: #0f172a; font-size: 16px; }
.computer-project > header span { margin-top: 4px; color: #64748b; font-size: 10px; }
.computer-project > header b { color: #0f172a; font-size: 18px; }
.computer-project__bar { height: 5px; margin: 12px 0 10px; overflow: hidden; border-radius: 4px; background: #e2e8f0; }
.computer-project__bar i { display: block; min-width: 3px; height: 100%; border-radius: inherit; background: #2563eb; }
.computer-project__meta { display: flex; flex-wrap: wrap; gap: 6px 14px; color: #64748b; font-size: 10px; }
.computer-project__reports { display: grid; gap: 8px; margin-top: 12px; }
.computer-project__reports article { padding: 10px 11px; border-radius: 7px; background: #f8fafc; }
.computer-project__reports article > div { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.computer-project__reports strong { overflow: hidden; color: #334155; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.computer-project__reports p { margin: 6px 0 0; color: #64748b; font-size: 11px; line-height: 1.55; }
.computer-codex-status { flex: 0 0 auto; padding: 2px 6px; border-radius: 999px; background: #dbeafe; color: #1d4ed8; font-size: 9px; font-weight: 700; }
.computer-codex-status--completed { background: #dcfce7; color: #15803d; }
.computer-codex-status--partial { background: #fef3c7; color: #a16207; }
.computer-codex-status--in_progress { background: #dbeafe; color: #1d4ed8; }
.computer-work-block-list { display: grid; gap: 9px; max-height: 420px; }
.computer-work-block { padding: 14px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; }
.computer-work-block--current { border-color: #bfdbfe; background: linear-gradient(135deg, #f8fbff, #fff); }
.computer-work-block header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.computer-work-block header strong,.computer-work-block header small { display: block; }
.computer-work-block header strong { margin-top: 4px; font-size: 17px; }
.computer-work-block header small,.computer-work-block time,.computer-work-block__status { color: var(--color-text-muted); font-size: 10px; }
.computer-work-block__status { color: #2563eb; font-weight: 700; }
.computer-work-block > p { margin: 10px 0; color: #334155; line-height: 1.7; }
.computer-work-block__metrics { display: flex; flex-wrap: wrap; gap: 8px 16px; color: #64748b; font-size: 11px; }
.computer-work-block__metrics b { color: #0f172a; }
.computer-work-block__details { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 8px; margin: 12px 0 0; }
.computer-work-block__details div { padding: 9px 10px; border-radius: 6px; background: #f8fafc; }
.computer-work-block__details dt { color: #64748b; font-size: 10px; }
.computer-work-block__details dd { margin: 4px 0 0; color: #334155; line-height: 1.5; }
.computer-analysis-state { padding: 16px; border-radius: 8px; background: #f8fafc; }
.computer-analysis-state p { margin: 6px 0; color: #475569; }
.computer-analysis-state small { color: #64748b; }
.computer-evidence-button { margin-top: 12px; }

.computer-insight-list,
.computer-plan-assessments {
  display: grid;
  gap: 9px;
  max-height: 320px;
}

.computer-insight-list article,
.computer-plan-assessments article,
.computer-topic-list article {
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 7px;
  background: #fff;
}

.computer-insight-list header,
.computer-plan-assessments article > div,
.computer-topic-list article > div,
.computer-daily-log > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.computer-insight-list time,
.computer-insight-list small,
.computer-plan-assessments span,
.computer-topic-list small,
.computer-daily-log span,
.computer-daily-log small {
  color: var(--color-text-muted);
  font-size: 10px;
}

.computer-insight-list strong { display: block; margin-top: 8px; }
.computer-insight-list p,
.computer-plan-assessments p,
.computer-topic-list p,
.computer-daily-log p { margin: 6px 0; color: #475569; line-height: 1.65; }
.insight-state { padding: 2px 6px; border-radius: 4px; background: #f1f5f9; color: #475569; font-size: 10px; }
.insight-state--complete { background: #dcfce7; color: #166534; }
.insight-state--failed { background: #fee2e2; color: #991b1b; }
.computer-topic-list { display: grid; gap: 9px; }
.computer-daily-log { padding: 4px 0; }
.computer-daily-log > div strong { font-size: 17px; }
.computer-reminder-list { display: grid; gap: 9px; max-height: 320px; overflow: auto; }
.computer-reminder-list article { padding: 12px; border: 1px solid #e5e7eb; border-radius: 7px; background: #fff; }
.computer-reminder-list article > div { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.computer-reminder-list p { margin: 6px 0 0; color: #475569; line-height: 1.6; }

.computer-activity-map-frame {
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  gap: 10px;
}

.computer-map-index {
  color: #475569;
  font-size: 12px;
}

.computer-map-index__spacer {
  height: 39px;
}

.computer-map-index strong {
  display: flex;
  align-items: center;
  height: 48px;
  margin-top: 10px;
}

.computer-map-index strong:first-of-type {
  height: 54px;
}

.computer-activity-map-scroll {
  min-width: 0;
  padding: 3px 0 8px;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  scrollbar-gutter: stable;
}

.computer-activity-map {
  min-width: 1680px;
}

.computer-map-axis {
  margin-left: 4px;
}

.computer-map-row {
  display: block;
}

@media (max-width: 760px) {
  .computer-insights-grid { grid-template-columns: 1fr; }
  .computer-project-list { grid-template-columns: 1fr; }
  .computer-activity-map-frame {
    grid-template-columns: 82px minmax(0, 1fr);
    gap: 8px;
  }

  .computer-activity-map {
    min-width: 1320px;
  }
}
</style>
