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

const { t } = useI18n(); const toast = useToast(); const queryClient = useQueryClient();
const coursesQuery = useQuery({ queryKey: ["courses"], queryFn: courseApi.list });
const selected = ref<CourseEvent | null>(null); const natural = ref("");
const form = reactive<CoursePayload>({ courseName: "", teacher: "", location: "", semesterStart: "", weekDay: 1, startWeek: 1, endWeek: 16, weekMode: "all", stTime: "08:00", endTime: "09:40", desc: "", prio: "mid" as Priority });
watch(selected, (course) => { if (!course) return; Object.assign(form, { courseName: course.courseName || course.title, teacher: course.teacher ?? "", location: course.location ?? "", semesterStart: course.semesterStart ?? course.stDate ?? "", weekDay: Number(course.weekDay), startWeek: course.startWeek ?? 1, endWeek: course.endWeek ?? 16, weekMode: course.weekMode ?? "all", stTime: course.stTime, endTime: course.endTime, desc: course.desc ?? "", prio: course.prio }); });
const byDay = computed(() => Array.from({ length: 7 }, (_, index) => (coursesQuery.data.value ?? []).filter((course) => Number(course.weekDay) === index + 1)));
const saveMutation = useMutation({ mutationFn: () => selected.value ? eventApi.update(selected.value.evtId, form as unknown as Record<string, unknown>) : courseApi.create(form), onSuccess: async () => { toast.success(selected.value ? t("course.updated") : t("course.created")); selected.value = null; await queryClient.invalidateQueries({ queryKey: ["courses"] }); } });
const syncMutation = useMutation({ mutationFn: courseApi.sync, onSuccess: () => toast.success(t("course.updated")) });
const parseMutation = useMutation({ mutationFn: () => aiApi.parse(natural.value, "create_course"), onSuccess: (data) => Object.assign(form, data) });
function reset() { selected.value = null; Object.assign(form, { courseName: "", teacher: "", location: "", semesterStart: "", weekDay: 1, startWeek: 1, endWeek: 16, weekMode: "all", stTime: "08:00", endTime: "09:40", desc: "", prio: "mid" }); }
</script>
<template>
  <section class="page-heading"><div><h1>{{ t("course.title") }}</h1><p>{{ t("course.subtitle") }}</p></div></section>
  <BaseCard title="Natural language"><div class="natural-input"><textarea v-model="natural" rows="2" /><button class="button button--primary" @click="parseMutation.mutate()">{{ t("add.parse") }}</button></div></BaseCard>
  <section class="course-layout">
    <div class="stack">
      <BaseCard title="Weekly timetable"><div class="timetable"><div v-for="(items, index) in byDay" :key="index" class="timetable-day"><strong>{{ index + 1 }}</strong><button v-for="course in items" :key="course.evtId" @click="selected = course"><span>{{ course.stTime }}–{{ course.endTime }}</span>{{ course.courseName || course.title }}<small>{{ course.location }}</small></button></div></div></BaseCard>
      <BaseCard title="Courses"><div class="event-list"><article v-for="course in coursesQuery.data.value ?? []" :key="course.evtId" class="course-row"><button class="course-row__main" type="button" @click="selected = course"><strong>{{ course.courseName || course.title }}</strong><span>{{ course.stTime }}–{{ course.endTime }} · week {{ course.startWeek }}–{{ course.endWeek }}</span></button><button class="button button--ghost" type="button" @click="syncMutation.mutate(course.evtId)">{{ t("course.sync") }}</button></article><EmptyState v-if="!(coursesQuery.data.value ?? []).length" /></div></BaseCard>
    </div>
    <BaseCard :title="selected ? t('common.edit') : t('common.create')"><form class="form-grid" @submit.prevent="saveMutation.mutate()">
      <label class="field field--wide"><span>{{ t("course.name") }}</span><input v-model="form.courseName" required /></label>
      <label class="field"><span>{{ t("course.teacher") }}</span><input v-model="form.teacher" /></label><label class="field"><span>{{ t("course.location") }}</span><input v-model="form.location" /></label>
      <label class="field field--wide"><span>{{ t("course.semesterStart") }}</span><input v-model="form.semesterStart" type="date" required /></label>
      <label class="field"><span>{{ t("course.weekday") }}</span><select v-model.number="form.weekDay"><option v-for="day in 7" :key="day" :value="day">{{ day }}</option></select></label><label class="field"><span>{{ t("course.weekMode") }}</span><select v-model="form.weekMode"><option value="all">all</option><option value="odd">odd</option><option value="even">even</option></select></label>
      <label class="field"><span>{{ t("course.startWeek") }}</span><input v-model.number="form.startWeek" type="number" min="1" /></label><label class="field"><span>{{ t("course.endWeek") }}</span><input v-model.number="form.endWeek" type="number" min="1" /></label>
      <label class="field"><span>{{ t("course.startTime") }}</span><input v-model="form.stTime" type="time" /></label><label class="field"><span>{{ t("course.endTime") }}</span><input v-model="form.endTime" type="time" /></label>
      <label class="field field--wide"><span>{{ t("event.form.description") }}</span><textarea v-model="form.desc" rows="3" /></label>
      <div class="form-actions field--wide"><button class="button button--primary" type="submit">{{ t("common.save") }}</button><button class="button" type="button" @click="reset">{{ t("common.cancel") }}</button></div>
    </form></BaseCard>
  </section>
</template>
