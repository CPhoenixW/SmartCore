<script setup lang="ts">
import { reactive, watch } from "vue";
import DdlPlanEditor from "./DdlPlanEditor.vue";
import DdlReminderEditor from "./DdlReminderEditor.vue";
import type { DdlPlan, DdlReminder, EventStatus, Priority, SmartCoreEvent } from "@/types/event";
import { getEventPrimaryTime, localInputToIso, toLocalInput } from "@/utils/date";

const props = defineProps<{ event: SmartCoreEvent; busy?: boolean }>();
const emit = defineEmits<{ save: [payload: Record<string, unknown>]; done: []; cancel: [] }>();
const form = reactive({ title: "", desc: "", stat: "todo" as EventStatus, prio: "mid" as Priority, time: "", durationMin: 30, hardDdl: false, plans: [] as DdlPlan[], ddlReminders: [] as DdlReminder[] });

watch(
  () => props.event,
  (event) => Object.assign(form, {
    title: event.title,
    desc: event.desc ?? "",
    stat: event.stat,
    prio: event.prio,
    time: toLocalInput(getEventPrimaryTime(event)),
    durationMin: event.evtType === "plan" ? event.durationMin : 30,
    hardDdl: event.evtType === "ddl" ? event.hardDdl : false,
    plans: event.evtType === "ddl" ? structuredClone(event.plans ?? []) : [],
    ddlReminders: event.evtType === "ddl" ? structuredClone(event.ddlReminders ?? []) : [],
  }),
  { immediate: true, deep: true },
);

function save() {
  const time = localInputToIso(form.time);
  if (!form.title.trim() || !time) return;
  const payload: Record<string, unknown> = { title: form.title.trim(), desc: form.desc.trim() || null, stat: form.stat, prio: form.prio };
  if (props.event.evtType === "plan") Object.assign(payload, { stTime: time, durationMin: Math.max(1, form.durationMin) });
  if (props.event.evtType === "remind") payload.triggerTime = time;
  if (props.event.evtType === "ddl") {
    const enabledPlans = form.plans.filter((plan) => plan.enabled !== false && plan.stTime);
    const enabledReminders = form.ddlReminders.filter((reminder) => reminder.enabled !== false);
    if (enabledReminders.some((reminder) => !reminder.title?.trim() || !reminder.triggerTime)) return;
    Object.assign(payload, { endTime: time, hardDdl: form.hardDdl, plans: enabledPlans, ddlReminders: enabledReminders });
  }
  emit("save", payload);
}
</script>

<template>
  <form class="form-grid" @submit.prevent="save">
    <label class="field field--wide"><span>{{ $t("event.form.title") }}</span><input v-model="form.title" required /></label>
    <label class="field field--wide"><span>{{ $t("event.form.description") }}</span><textarea v-model="form.desc" rows="3" /></label>
    <label class="field"><span>{{ $t("event.form.status") }}</span><select v-model="form.stat"><option value="todo">{{ $t("event.status.todo") }}</option><option value="done">{{ $t("event.status.done") }}</option><option value="cancelled">{{ $t("event.status.cancelled") }}</option></select></label>
    <label class="field"><span>{{ $t("event.form.priority") }}</span><select v-model="form.prio"><option value="low">{{ $t("event.priority.low") }}</option><option value="mid">{{ $t("event.priority.mid") }}</option><option value="high">{{ $t("event.priority.high") }}</option></select></label>
    <label class="field"><span>{{ event.evtType === 'ddl' ? $t('event.form.deadline') : event.evtType === 'remind' ? $t('event.form.triggerTime') : $t('event.form.startTime') }}</span><input v-model="form.time" type="datetime-local" required /></label>
    <label v-if="event.evtType === 'plan'" class="field"><span>{{ $t("event.form.duration") }}</span><input v-model.number="form.durationMin" type="number" min="1" /></label>
    <label v-if="event.evtType === 'ddl'" class="check-field field--wide"><input v-model="form.hardDdl" type="checkbox" />{{ $t("event.form.hardDdl") }}</label>
    <div v-if="event.evtType === 'ddl'" class="field--wide"><DdlPlanEditor v-model="form.plans" /></div>
    <div v-if="event.evtType === 'ddl'" class="field--wide"><h3>{{ $t("event.form.linkedReminders") }}</h3><DdlReminderEditor v-model="form.ddlReminders" /></div>
    <div class="form-actions field--wide">
      <button class="button button--primary" type="submit" :disabled="busy">{{ $t("common.save") }}</button>
      <button v-if="event.stat !== 'done'" class="button" type="button" :disabled="busy" @click="$emit('done')">{{ $t("event.status.done") }}</button>
      <button class="button button--danger" type="button" :disabled="busy" @click="$emit('cancel')">{{ $t("common.cancel") }}</button>
    </div>
  </form>
</template>
