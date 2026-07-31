<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import PageHeader from "@/components/base/PageHeader.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import PreviewActionButton from "@/components/base/PreviewActionButton.vue";
import { dailySummaryApi } from "@/api/dailySummary";
import { useToast } from "@/composables/useToast";
import { addDays, formatDateTime, todayKey } from "@/utils/date";

interface InlinePart {
  text: string;
  bold: boolean;
}

interface ReportLine {
  kind: "blank" | "heading" | "bullet" | "paragraph";
  parts: InlinePart[];
}

const { t, locale } = useI18n();
const toast = useToast();
const queryClient = useQueryClient();
const selectedDate = ref(todayKey());
const search = ref("");
const editing = ref(false);
const draft = ref("");
const reportsQuery = useQuery({
  queryKey: computed(() => [
    "daily-summaries",
    selectedDate.value,
    search.value.trim(),
  ]),
  queryFn: () => dailySummaryApi.list({
    date: selectedDate.value,
    text: search.value.trim() || undefined,
  }),
  refetchInterval: 15_000,
});
const report = computed(() => reportsQuery.data.value?.[0] ?? null);
const title = computed(() => (
  selectedDate.value === todayKey()
    ? t("dailySummary.todayTitle")
    : t("dailySummary.dateTitle", { date: selectedDate.value })
));
const generatedAt = computed(() => (
  report.value?.generatedAt
    ? formatDateTime(report.value.generatedAt, locale.value)
    : ""
));

watch(report, (value) => {
  if (!editing.value) draft.value = String(value?.content ?? "");
}, { immediate: true });

watch(selectedDate, () => {
  editing.value = false;
});

const save = useMutation({
  mutationFn: () => dailySummaryApi.update(report.value!.summaryId, {
    content: draft.value.trim(),
    expectedUpdatedAt: report.value!.updatedAt,
  }),
  onSuccess: async (updated) => {
    draft.value = String(updated.content ?? "");
    editing.value = false;
    await queryClient.invalidateQueries({ queryKey: ["daily-summaries"] });
    toast.success(t("dailySummary.saved"));
  },
  onError: (error) => toast.error(error instanceof Error ? error.message : t("dailySummary.saveFailed")),
});

function startEdit() {
  if (!report.value?.content) return;
  draft.value = report.value.content;
  editing.value = true;
}

function cancelEdit() {
  draft.value = String(report.value?.content ?? "");
  editing.value = false;
}

function inlineParts(value: string): InlinePart[] {
  const parts: InlinePart[] = [];
  const pattern = /\*\*(.+?)\*\*/g;
  let cursor = 0;
  for (const match of value.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > cursor) parts.push({ text: value.slice(cursor, index), bold: false });
    parts.push({ text: match[1] ?? "", bold: true });
    cursor = index + match[0].length;
  }
  if (cursor < value.length) parts.push({ text: value.slice(cursor), bold: false });
  return parts.length ? parts : [{ text: value, bold: false }];
}

const reportLines = computed<ReportLine[]>(() => (
  String(report.value?.content ?? "").split("\n").map((raw) => {
    const line = raw.trim();
    if (!line) return { kind: "blank", parts: [] };
    if (/^#{1,3}\s+/.test(line)) {
      return { kind: "heading", parts: inlineParts(line.replace(/^#{1,3}\s+/, "")) };
    }
    if (/^[-*]\s+/.test(line)) {
      return { kind: "bullet", parts: inlineParts(line.replace(/^[-*]\s+/, "")) };
    }
    return { kind: "paragraph", parts: inlineParts(line) };
  })
));

function moveDate(days: number) {
  selectedDate.value = addDays(selectedDate.value, days);
}
</script>

<template>
  <PageHeader :title="t('dailySummary.title')" :subtitle="t('dailySummary.subtitle')" />

  <div class="daily-summary-toolbar">
    <button class="button" type="button" @click="moveDate(-1)">{{ t("common.previous") }}</button>
    <input v-model="selectedDate" type="date" :aria-label="t('dailySummary.selectDate')" />
    <button class="button" type="button" @click="selectedDate = todayKey()">{{ t("common.today") }}</button>
    <button class="button" type="button" @click="moveDate(1)">{{ t("common.next") }}</button>
    <label class="daily-summary-search">
      <span>⌕</span>
      <input v-model.trim="search" :placeholder="t('dailySummary.searchPlaceholder')" />
    </label>
  </div>

  <BaseCard :title="title">
    <template #actions>
      <span v-if="report" class="summary-status" :class="`summary-status--${report.stat}`">
        {{ t(`dailySummary.status.${report.stat}`) }}
      </span>
      <PreviewActionButton v-if="report?.content && !editing" :label="t('common.edit')" @click="startEdit" />
    </template>
    <div v-if="reportsQuery.isPending.value" class="daily-summary-state">{{ t("common.loading") }}</div>
    <div v-else-if="report?.stat === 'queued'" class="daily-summary-state">{{ t("dailySummary.queued") }}</div>
    <div v-else-if="report?.stat === 'failed'" class="daily-summary-state daily-summary-state--failed">
      {{ t("dailySummary.failed") }}
    </div>
    <form v-else-if="editing && report" class="daily-summary-editor" @submit.prevent="save.mutate()">
      <textarea v-model="draft" rows="18" :aria-label="t('dailySummary.editContent')" />
      <div class="form-actions">
        <button class="button" type="button" @click="cancelEdit">{{ t("common.cancel") }}</button>
        <button class="button button--primary" :disabled="save.isPending.value || !draft.trim()">{{ save.isPending.value ? t("common.saving") : t("common.save") }}</button>
      </div>
    </form>
    <article v-else-if="report?.content" class="daily-summary-report daily-summary-report--editable" @dblclick="startEdit">
      <template v-for="(line, index) in reportLines" :key="index">
        <div v-if="line.kind === 'blank'" class="report-space" />
        <h3 v-else-if="line.kind === 'heading'">
          <template v-for="(part, partIndex) in line.parts" :key="partIndex">
            <strong v-if="part.bold">{{ part.text }}</strong><template v-else>{{ part.text }}</template>
          </template>
        </h3>
        <p v-else :class="{ 'report-bullet': line.kind === 'bullet' }">
          <template v-for="(part, partIndex) in line.parts" :key="partIndex">
            <strong v-if="part.bold">{{ part.text }}</strong><template v-else>{{ part.text }}</template>
          </template>
        </p>
      </template>
      <footer v-if="generatedAt">{{ t("dailySummary.generatedAt", { time: generatedAt }) }}</footer>
    </article>
    <EmptyState
      v-else
      :text="search ? t('dailySummary.noMatch') : t('dailySummary.empty')"
    />
  </BaseCard>
</template>

<style scoped>
.daily-summary-toolbar {
  display: grid;
  grid-template-columns: auto minmax(170px, 230px) auto auto minmax(240px, 1fr);
  gap: 12px;
  margin-bottom: 18px;
}
.daily-summary-toolbar > input,
.daily-summary-search {
  min-width: 0;
  min-height: 44px;
  border: 1px solid var(--border-color);
  border-radius: 11px;
  background: #fff;
}
.daily-summary-toolbar > input {
  padding: 10px 12px;
  color: var(--color-text);
}
.daily-summary-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 13px;
  color: var(--color-text-muted);
}
.daily-summary-search input {
  width: 100%;
  border: 0;
  outline: 0;
}
.summary-status {
  padding: 5px 9px;
  border-radius: 999px;
  background: var(--color-surface-muted);
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 750;
}
.summary-status--complete { background: #ecfdf5; color: var(--color-success); }
.summary-status--failed { background: #fef2f2; color: var(--color-danger); }
.daily-summary-state {
  padding: 48px 16px;
  text-align: center;
  color: var(--color-text-muted);
}
.daily-summary-state--failed { color: var(--color-danger); }
.daily-summary-editor { display: grid; gap: 14px; max-width: 980px; }
.daily-summary-editor textarea { width: 100%; min-height: 420px; padding: 16px; border: 1px solid var(--border-color); border-radius: 8px; outline: 0; resize: vertical; color: var(--color-text); font: inherit; line-height: 1.65; }
.daily-summary-editor textarea:focus { border-color: #60a5fa; box-shadow: 0 0 0 3px rgb(96 165 250 / 15%); }
.daily-summary-report {
  max-width: 860px;
  padding: 8px 2px;
  color: var(--color-text);
  line-height: 1.75;
}
.daily-summary-report--editable { cursor: text; }
.daily-summary-report h3 { margin: 18px 0 7px; font-size: 17px; }
.daily-summary-report p { margin: 6px 0; }
.daily-summary-report .report-bullet { position: relative; padding-left: 18px; }
.daily-summary-report .report-bullet::before { position: absolute; left: 2px; content: "•"; color: var(--color-primary); }
.report-space { height: 8px; }
.daily-summary-report footer {
  margin-top: 26px;
  padding-top: 14px;
  border-top: 1px solid var(--border-color);
  color: var(--color-text-muted);
  font-size: 12px;
}
@media (max-width: 880px) {
  .daily-summary-toolbar { grid-template-columns: 1fr 1fr; }
  .daily-summary-search { grid-column: 1 / -1; }
}
</style>
