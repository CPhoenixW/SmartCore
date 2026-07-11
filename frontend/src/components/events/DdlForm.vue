<script setup lang="ts">
import { reactive, watch } from "vue";
import { z } from "zod";
import DdlPlanEditor from "./DdlPlanEditor.vue";
import type { CreateDdlPayload, DdlPlan, Priority } from "@/types/event";
import { defaultDdlPlans, localInputToIso, toLocalInput } from "@/utils/date";
const props = defineProps<{ initial?: Partial<CreateDdlPayload> }>();
const emit = defineEmits<{ submit: [payload: CreateDdlPayload] }>();
const schema = z.object({ title: z.string().trim().min(1), endTime: z.string().min(1), prio: z.enum(["low", "mid", "high"]) });
const defaultEnd = new Date(Date.now() + 86_400_000).toISOString();
const form = reactive({ title: "", desc: "", endTime: toLocalInput(defaultEnd), hardDdl: false, prio: "high" as Priority, plans: defaultDdlPlans(defaultEnd) as DdlPlan[] });
watch(() => props.initial, (value) => { if (!value) return; Object.assign(form, value, { endTime: toLocalInput(value.endTime) || form.endTime, plans: value.plans ? structuredClone(value.plans) : form.plans }); }, { immediate: true, deep: true });
function resetPlans() { form.plans = defaultDdlPlans(localInputToIso(form.endTime)); }
function submit() { const parsed = schema.parse(form); emit("submit", { ...parsed, desc: form.desc || null, hardDdl: form.hardDdl, endTime: localInputToIso(parsed.endTime), plans: form.plans }); }
</script>
<template><form class="form-grid" @submit.prevent="submit">
  <label class="field field--wide"><span>{{ $t("event.form.title") }}</span><input v-model="form.title" required /></label>
  <label class="field field--wide"><span>{{ $t("event.form.description") }}</span><textarea v-model="form.desc" rows="3" /></label>
  <label class="field"><span>{{ $t("event.form.deadline") }}</span><input v-model="form.endTime" type="datetime-local" required @change="resetPlans" /></label>
  <label class="field"><span>{{ $t("event.form.priority") }}</span><select v-model="form.prio"><option value="low">{{ $t("event.priority.low") }}</option><option value="mid">{{ $t("event.priority.mid") }}</option><option value="high">{{ $t("event.priority.high") }}</option></select></label>
  <label class="check-field field--wide"><input v-model="form.hardDdl" type="checkbox" />{{ $t("event.form.hardDdl") }}</label>
  <div class="field--wide"><h3>{{ $t("event.form.plans") }}</h3><DdlPlanEditor v-model="form.plans" /></div>
  <div class="form-actions field--wide"><button class="button button--primary" type="submit">{{ $t("common.create") }}</button></div>
</form></template>
