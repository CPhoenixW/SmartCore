<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import PageHeader from "@/components/base/PageHeader.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import PreviewActionButton from "@/components/base/PreviewActionButton.vue";
import EventPreviewCard from "@/components/events/EventPreviewCard.vue";
import { aiApi } from "@/api/ai";
import { courseApi } from "@/api/course";
import { eventApi } from "@/api/event";
import { useToast } from "@/composables/useToast";
import type { CoursePayload } from "@/types/course";
import type { CourseEvent, Priority } from "@/types/event";
import { formatDateTime, normalizeSearch } from "@/utils/date";

const { t } = useI18n();
const toast = useToast();
const queryClient = useQueryClient();
const coursesQuery = useQuery({ queryKey: ["courses"], queryFn: courseApi.list });
const selected = ref<CourseEvent | null>(null);
const editing = ref(false);
const natural = ref("");
const search = ref("");
const form = reactive<CoursePayload>({ courseName: "", teacher: "", location: "", semesterStart: "", weekDay: 1, startWeek: 1, endWeek: 16, weekMode: "all", stTime: "08:00", endTime: "09:40", desc: "", prio: "mid" as Priority });

function fillForm(course: CourseEvent | null) {
  if (!course) {
    Object.assign(form, { courseName: "", teacher: "", location: "", semesterStart: "", weekDay: 1, startWeek: 1, endWeek: 16, weekMode: "all", stTime: "08:00", endTime: "09:40", desc: "", prio: "mid" });
    return;
  }
  Object.assign(form, {
    courseName: course.courseName || course.title,
    teacher: course.teacher ?? "",
    location: course.location ?? "",
    semesterStart: course.semesterStart ?? course.stDate ?? "",
    weekDay: Number(course.weekDay),
    startWeek: course.startWeek ?? 1,
    endWeek: course.endWeek ?? 16,
    weekMode: course.weekMode ?? "all",
    stTime: course.stTime,
    endTime: course.endTime,
    desc: course.desc ?? "",
    prio: course.prio,
  });
}

watch(selected, fillForm);
const activeCourses = computed(() =>
  (coursesQuery.data.value ?? []).filter((course) => course.stat !== "cancelled"),
);
const filteredCourses = computed(() => {
  const query = normalizeSearch(search.value);
  return activeCourses.value.filter((course) => {
    if (!query) return true;
    return normalizeSearch([course.courseName, course.title, course.teacher, course.location, course.desc, course.semesterStart, course.stDate, course.endDate, course.stTime, course.endTime, course.weekDay, course.weekMode].filter(Boolean).join(" ")).includes(query);
  });
});
watch(filteredCourses, (courses) => {
  if (!courses.length) {
    selected.value = null;
    return;
  }
  if (editing.value) return;
  choose(courses.find((course) => course.evtId === selected.value?.evtId) ?? courses[0]!);
}, { immediate: true });
const byDay = computed(() =>
  Array.from({ length: 7 }, (_, index) =>
    filteredCourses.value
      .filter((course) => course.stat !== "cancelled" && Number(course.weekDay) === index + 1)
      .sort((a, b) => String(a.stTime).localeCompare(String(b.stTime))),
  ),
);
const estimatedCount = computed(() => {
  if (!form.semesterStart || form.endWeek < form.startWeek) return 0;
  let count = 0;
  for (let week = form.startWeek; week <= form.endWeek; week += 1) {
    if (form.weekMode === "odd" && week % 2 === 0) continue;
    if (form.weekMode === "even" && week % 2 === 1) continue;
    count += 1;
  }
  return count;
});
const previewTime = computed(() => {
  if (selected.value?.nextOccurrence?.stTime) return selected.value.nextOccurrence.stTime;
  if (!form.semesterStart || !form.stTime) return "";
  const semester = new Date(`${form.semesterStart}T12:00:00`);
  if (Number.isNaN(semester.getTime())) return "";
  const monday = new Date(semester);
  monday.setDate(semester.getDate() - ((semester.getDay() + 6) % 7));
  monday.setDate(monday.getDate() + (Math.max(1, form.startWeek) - 1) * 7 + Math.max(0, form.weekDay - 1));
  const [hour = "00", minute = "00"] = form.stTime.split(":");
  monday.setHours(Number(hour), Number(minute), 0, 0);
  return monday.toISOString();
});
const scheduleText = computed(() => t("course.scheduleSummary", { start: form.stTime, end: form.endTime, startWeek: form.startWeek, endWeek: form.endWeek }));

function validateForm() {
  if (!form.courseName.trim() || !form.semesterStart || !form.stTime || !form.endTime) throw new Error(t("course.validation.required"));
  if (form.endWeek < form.startWeek) throw new Error(t("course.validation.weekRange"));
  if (form.endTime <= form.stTime) throw new Error(t("course.validation.timeRange"));
}

const saveMutation = useMutation({
  mutationFn: async () => {
    validateForm();
    const payload = { ...form, courseName: form.courseName.trim(), title: form.courseName.trim(), teacher: form.teacher || null, location: form.location || null, desc: form.desc || null };
    return selected.value ? eventApi.update(selected.value.evtId, payload as unknown as Record<string, unknown>) : courseApi.create(payload);
  },
  onSuccess: async () => { toast.success(selected.value ? t("course.updated") : t("course.created")); selected.value = null; editing.value = false; fillForm(null); await queryClient.invalidateQueries({ queryKey: ["courses"] }); await queryClient.invalidateQueries({ queryKey: ["events"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const syncMutation = useMutation({
  mutationFn: courseApi.sync,
  onSuccess: async () => { toast.success(t("course.syncSuccess")); await queryClient.invalidateQueries({ queryKey: ["courses"] }); await queryClient.invalidateQueries({ queryKey: ["events"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const syncAllMutation = useMutation({
  mutationFn: async () => {
    for (const course of activeCourses.value) await courseApi.sync(course.evtId);
  },
  onSuccess: async () => { toast.success(t("course.syncAllSuccess")); await queryClient.invalidateQueries({ queryKey: ["courses"] }); await queryClient.invalidateQueries({ queryKey: ["events"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const deleteMutation = useMutation({
  mutationFn: (id: string) => eventApi.cancel(id),
  onSuccess: async () => { toast.success(t("course.cancelSuccess")); selected.value = null; editing.value = false; fillForm(null); await queryClient.invalidateQueries({ queryKey: ["courses"] }); await queryClient.invalidateQueries({ queryKey: ["events"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const parseMutation = useMutation({
  mutationFn: () => aiApi.parse<Record<string, unknown>>(natural.value, "create_course"),
  onSuccess: (data) => { selected.value = null; editing.value = true; fillForm(null); Object.assign(form, data); toast.success(t("course.parsed")); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const busy = computed(() => saveMutation.isPending.value || syncMutation.isPending.value || syncAllMutation.isPending.value || deleteMutation.isPending.value);
function choose(course: CourseEvent) { selected.value = course; editing.value = false; fillForm(course); }
function editCourse(course: CourseEvent) { selected.value = course; editing.value = true; fillForm(course); }
function startNew() { selected.value = null; editing.value = true; fillForm(null); }
function cancelEdit() {
  editing.value = false;
  const course = selected.value ?? filteredCourses.value[0] ?? null;
  selected.value = course;
  fillForm(course);
}
</script>

<template>
  <div class="dual-scroll-page">
    <PageHeader :title="t('course.title')" :subtitle="t('course.subtitle')"><template #actions><button class="button" :disabled="busy" @click="syncAllMutation.mutate()">{{ t("course.syncAll") }}</button><button class="button button--primary" @click="startNew">{{ t("course.new") }}</button></template></PageHeader>
    <section class="split-scroll-layout split-scroll-layout--course">
      <div class="split-scroll-column split-scroll-column--main" data-staged-wheel-scroll>
        <div class="stack">
          <BaseCard :title="t('course.natural')"><div class="natural-input"><textarea v-model="natural" rows="2" :placeholder="t('course.naturalPlaceholder')" /><button class="button button--primary" :disabled="!natural.trim() || parseMutation.isPending.value" @click="parseMutation.mutate()">{{ t("add.parse") }}</button></div></BaseCard>
          <BaseCard :title="t('course.timetable')"><template #actions><input v-model="search" class="compact-search" :placeholder="t('course.searchPlaceholder')" /></template><div class="timetable-scroll"><div class="timetable timetable--large"><div v-for="(items, index) in byDay" :key="index" class="timetable-day"><strong>{{ t(`course.weekdayNames.${index + 1}`) }}</strong><button v-for="course in items" :key="course.evtId" :class="{ selected: selected?.evtId === course.evtId }" @click="choose(course)" @dblclick="editCourse(course)"><span>{{ course.stTime }}–{{ course.endTime }}</span>{{ course.courseName || course.title }}<small>{{ [course.location, course.teacher].filter(Boolean).join(' · ') || t('common.notSet') }}</small><small>{{ t("course.weeksAndCount", { start: course.startWeek, end: course.endWeek, count: course.occurrenceCount ?? 0 }) }}</small></button></div></div></div></BaseCard>
          <BaseCard :title="t('course.list')"><div class="event-list"><article v-for="course in filteredCourses" :key="course.evtId" class="course-row" :class="{ cancelled: course.stat === 'cancelled' }"><button class="course-row__main" type="button" @click="choose(course)" @dblclick="editCourse(course)"><strong>{{ course.courseName || course.title }}</strong><span>{{ course.stTime }}–{{ course.endTime }} · {{ t("course.weekRange", { start: course.startWeek, end: course.endWeek }) }} · {{ t(`course.weekModeValues.${course.weekMode}`) }}</span><span>{{ course.location || t('common.notSet') }} · {{ course.teacher || t('common.notSet') }} · {{ t("course.occurrenceCount", { count: course.occurrenceCount ?? 0 }) }}</span><span v-if="course.nextOccurrence?.stTime">{{ t("course.nextClass") }}：{{ formatDateTime(course.nextOccurrence.stTime) }}</span></button><button class="button button--ghost" type="button" :disabled="busy || course.stat === 'cancelled'" @click="syncMutation.mutate(course.evtId)">{{ t("course.sync") }}</button></article><EmptyState v-if="!filteredCourses.length" /></div></BaseCard>
        </div>
      </div>
      <aside class="split-scroll-column split-scroll-column--side" data-staged-wheel-scroll>
        <div class="stack">
          <BaseCard v-if="selected && !editing" :title="t('preview.title')">
            <template #actions><PreviewActionButton :label="t('common.edit')" @click="editing = true" /></template>
            <EventPreviewCard type="course" :title="form.courseName" :description="form.desc" :priority="form.prio" :status="selected.stat" :time="previewTime" :location="form.location" :teacher="form.teacher" :schedule="scheduleText" />
          </BaseCard>
          <BaseCard v-else-if="editing" :title="selected ? t('course.edit') : t('course.create')">
            <template #actions><PreviewActionButton action="close" :label="t('common.close')" @click="cancelEdit" /></template>
            <form class="form-grid" @submit.prevent="saveMutation.mutate()">
            <label class="field field--wide"><span>{{ t("course.name") }}</span><input v-model="form.courseName" :placeholder="t('course.namePlaceholder')" required /></label>
            <label class="field"><span>{{ t("course.teacher") }}</span><input v-model="form.teacher" :placeholder="t('course.teacherPlaceholder')" /></label><label class="field"><span>{{ t("course.location") }}</span><input v-model="form.location" :placeholder="t('course.locationPlaceholder')" /></label>
            <label class="field field--wide"><span>{{ t("course.semesterStart") }}</span><input v-model="form.semesterStart" type="date" required /></label>
            <label class="field"><span>{{ t("course.weekday") }}</span><select v-model.number="form.weekDay"><option v-for="day in 7" :key="day" :value="day">{{ t(`course.weekdayNames.${day}`) }}</option></select></label><label class="field"><span>{{ t("course.weekMode") }}</span><select v-model="form.weekMode"><option value="all">{{ t("course.weekModeValues.all") }}</option><option value="odd">{{ t("course.weekModeValues.odd") }}</option><option value="even">{{ t("course.weekModeValues.even") }}</option></select></label>
            <label class="field"><span>{{ t("course.startWeek") }}</span><input v-model.number="form.startWeek" type="number" min="1" /></label><label class="field"><span>{{ t("course.endWeek") }}</span><input v-model.number="form.endWeek" type="number" min="1" /></label>
            <label class="field"><span>{{ t("course.startTime") }}</span><input v-model="form.stTime" type="time" /></label><label class="field"><span>{{ t("course.endTime") }}</span><input v-model="form.endTime" type="time" /></label>
            <label class="field"><span>{{ t("event.form.priority") }}</span><select v-model="form.prio"><option value="low">{{ t("event.priority.low") }}</option><option value="mid">{{ t("event.priority.mid") }}</option><option value="high">{{ t("event.priority.high") }}</option></select></label><div class="field summary-field"><span>{{ t("course.estimated") }}</span><strong>{{ t("course.estimatedValue", { plans: estimatedCount, reminders: estimatedCount * 2 }) }}</strong></div>
            <label class="field field--wide"><span>{{ t("event.form.description") }}</span><textarea v-model="form.desc" rows="3" :placeholder="t('event.placeholder.description')" /></label>
            <div class="form-actions field--wide"><button class="button button--primary" type="submit" :disabled="busy">{{ busy ? t("common.saving") : t("common.save") }}</button><button class="button" type="button" @click="cancelEdit">{{ t("common.cancel") }}</button><button v-if="selected" class="button button--danger" type="button" :disabled="busy" @click="deleteMutation.mutate(selected.evtId)">{{ t("common.delete") }}</button></div>
          </form></BaseCard>
          <BaseCard v-else><EmptyState /></BaseCard>
        </div>
      </aside>
    </section>
  </div>
</template>
