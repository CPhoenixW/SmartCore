<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
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
const filteredCourses = computed(() => {
  const query = normalizeSearch(search.value);
  return (coursesQuery.data.value ?? []).filter((course) => {
    if (!query) return true;
    return normalizeSearch([course.courseName, course.title, course.teacher, course.location, course.desc, course.semesterStart, course.stDate, course.endDate, course.stTime, course.endTime, course.weekDay, course.weekMode].filter(Boolean).join(" ")).includes(query);
  });
});
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

function validateForm() {
  if (!form.courseName.trim() || !form.semesterStart || !form.stTime || !form.endTime) throw new Error("请完整填写课程名称、学期开始日期和时间");
  if (form.endWeek < form.startWeek) throw new Error("结束周不能早于起始周");
  if (form.endTime <= form.stTime) throw new Error("下课时间必须晚于上课时间");
}

const saveMutation = useMutation({
  mutationFn: async () => {
    validateForm();
    const payload = { ...form, courseName: form.courseName.trim(), title: form.courseName.trim(), teacher: form.teacher || null, location: form.location || null, desc: form.desc || null };
    return selected.value ? eventApi.update(selected.value.evtId, payload as unknown as Record<string, unknown>) : courseApi.create(payload);
  },
  onSuccess: async () => { toast.success(selected.value ? t("course.updated") : t("course.created")); selected.value = null; fillForm(null); await queryClient.invalidateQueries({ queryKey: ["courses"] }); await queryClient.invalidateQueries({ queryKey: ["events"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const syncMutation = useMutation({
  mutationFn: courseApi.sync,
  onSuccess: async () => { toast.success("上课计划和提醒已重新生成"); await queryClient.invalidateQueries({ queryKey: ["courses"] }); await queryClient.invalidateQueries({ queryKey: ["events"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const syncAllMutation = useMutation({
  mutationFn: async () => {
    for (const course of (coursesQuery.data.value ?? []).filter((item) => item.stat !== "cancelled")) await courseApi.sync(course.evtId);
  },
  onSuccess: async () => { toast.success("全部课程计划已重新生成"); await queryClient.invalidateQueries({ queryKey: ["courses"] }); await queryClient.invalidateQueries({ queryKey: ["events"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const deleteMutation = useMutation({
  mutationFn: (id: string) => eventApi.cancel(id),
  onSuccess: async () => { toast.success("课程及未完成计划已取消"); selected.value = null; fillForm(null); await queryClient.invalidateQueries({ queryKey: ["courses"] }); await queryClient.invalidateQueries({ queryKey: ["events"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const parseMutation = useMutation({
  mutationFn: () => aiApi.parse<Record<string, unknown>>(natural.value, "create_course"),
  onSuccess: (data) => { selected.value = null; fillForm(null); Object.assign(form, data); toast.success("课程信息已填入表单"); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const busy = computed(() => saveMutation.isPending.value || syncMutation.isPending.value || syncAllMutation.isPending.value || deleteMutation.isPending.value);
function reset() { selected.value = null; fillForm(null); }
</script>

<template>
  <section class="page-heading"><div><h1>{{ t("course.title") }}</h1><p>{{ t("course.subtitle") }}</p></div><div class="heading-actions"><button class="button" :disabled="busy" @click="syncAllMutation.mutate()">{{ t("course.sync") }}</button><button class="button button--primary" @click="reset">新建课程</button></div></section>
  <BaseCard title="自然语言添加课程"><div class="natural-input"><textarea v-model="natural" rows="2" placeholder="例如：学期 2026-09-13 开始，高等数学，周二 8:00-9:40，第 1-16 周" /><button class="button button--primary" :disabled="!natural.trim() || parseMutation.isPending.value" @click="parseMutation.mutate()">{{ t("add.parse") }}</button></div></BaseCard>
  <section class="course-layout spaced-section">
    <div class="stack">
      <BaseCard title="周课表"><template #actions><input v-model="search" class="compact-search" :placeholder="t('common.search')" /></template><div class="timetable"><div v-for="(items, index) in byDay" :key="index" class="timetable-day"><strong>{{ index + 1 }}</strong><button v-for="course in items" :key="course.evtId" :class="{ selected: selected?.evtId === course.evtId }" @click="selected = course"><span>{{ course.stTime }}–{{ course.endTime }}</span>{{ course.courseName || course.title }}<small>{{ [course.location, course.teacher].filter(Boolean).join(' · ') || '—' }}</small><small>第 {{ course.startWeek }}–{{ course.endWeek }} 周 · {{ course.occurrenceCount ?? 0 }} 次</small></button></div></div></BaseCard>
      <BaseCard title="课程列表"><div class="event-list"><article v-for="course in filteredCourses" :key="course.evtId" class="course-row" :class="{ cancelled: course.stat === 'cancelled' }"><button class="course-row__main" type="button" @click="selected = course"><strong>{{ course.courseName || course.title }}</strong><span>{{ course.stTime }}–{{ course.endTime }} · 第 {{ course.startWeek }}–{{ course.endWeek }} 周 · {{ course.weekMode }}</span><span>{{ course.location || '—' }} · {{ course.teacher || '—' }} · 共 {{ course.occurrenceCount ?? 0 }} 次</span><span v-if="course.nextOccurrence?.stTime">下次：{{ formatDateTime(course.nextOccurrence.stTime) }}</span></button><button class="button button--ghost" type="button" :disabled="busy || course.stat === 'cancelled'" @click="syncMutation.mutate(course.evtId)">{{ t("course.sync") }}</button></article><EmptyState v-if="!filteredCourses.length" /></div></BaseCard>
    </div>
    <BaseCard :title="selected ? t('common.edit') : t('common.create')"><form class="form-grid" @submit.prevent="saveMutation.mutate()">
      <label class="field field--wide"><span>{{ t("course.name") }}</span><input v-model="form.courseName" required /></label>
      <label class="field"><span>{{ t("course.teacher") }}</span><input v-model="form.teacher" /></label><label class="field"><span>{{ t("course.location") }}</span><input v-model="form.location" /></label>
      <label class="field field--wide"><span>{{ t("course.semesterStart") }}</span><input v-model="form.semesterStart" type="date" required /></label>
      <label class="field"><span>{{ t("course.weekday") }}</span><select v-model.number="form.weekDay"><option v-for="day in 7" :key="day" :value="day">{{ day }}</option></select></label><label class="field"><span>{{ t("course.weekMode") }}</span><select v-model="form.weekMode"><option value="all">每周</option><option value="odd">单周</option><option value="even">双周</option></select></label>
      <label class="field"><span>{{ t("course.startWeek") }}</span><input v-model.number="form.startWeek" type="number" min="1" /></label><label class="field"><span>{{ t("course.endWeek") }}</span><input v-model.number="form.endWeek" type="number" min="1" /></label>
      <label class="field"><span>{{ t("course.startTime") }}</span><input v-model="form.stTime" type="time" /></label><label class="field"><span>{{ t("course.endTime") }}</span><input v-model="form.endTime" type="time" /></label>
      <label class="field"><span>{{ t("event.form.priority") }}</span><select v-model="form.prio"><option value="low">{{ t("event.priority.low") }}</option><option value="mid">{{ t("event.priority.mid") }}</option><option value="high">{{ t("event.priority.high") }}</option></select></label><div class="field summary-field"><span>预计生成</span><strong>{{ estimatedCount }} 个计划 / {{ estimatedCount * 2 }} 个提醒</strong></div>
      <label class="field field--wide"><span>{{ t("event.form.description") }}</span><textarea v-model="form.desc" rows="3" /></label>
      <div class="form-actions field--wide"><button class="button button--primary" type="submit" :disabled="busy">{{ t("common.save") }}</button><button class="button" type="button" @click="reset">{{ t("common.cancel") }}</button><button v-if="selected" class="button button--danger" type="button" :disabled="busy" @click="deleteMutation.mutate(selected.evtId)">{{ t("common.delete") }}</button></div>
    </form></BaseCard>
  </section>
</template>
