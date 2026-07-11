<script setup lang="ts">
import { reactive, watch } from "vue";
import { z } from "zod";
import type { CreateReminderPayload, Priority } from "@/types/event";
import { localInputToIso, toLocalInput } from "@/utils/date";
const props = defineProps<{ initial?: Partial<CreateReminderPayload> }>();
const emit = defineEmits<{ submit: [payload: CreateReminderPayload] }>();
const schema = z.object({ title: z.string().trim().min(1), triggerTime: z.string().min(1), prio: z.enum(["low", "mid", "high"]) });
const form = reactive({ title: "", desc: "", triggerTime: toLocalInput(new Date(Date.now() + 3_600_000).toISOString()), prio: "mid" as Priority });
watch(() => props.initial, (value) => { if (!value) return; Object.assign(form, value, { triggerTime: toLocalInput(value.triggerTime) || form.triggerTime }); }, { immediate: true, deep: true });
function submit() { const parsed = schema.parse(form); emit("submit", { ...parsed, desc: form.desc || null, triggerTime: localInputToIso(parsed.triggerTime) }); }
</script>
<template><form class="form-grid" @submit.prevent="submit">
  <label class="field field--wide"><span>{{ $t("event.form.title") }}</span><input v-model="form.title" required /></label>
  <label class="field field--wide"><span>{{ $t("event.form.description") }}</span><textarea v-model="form.desc" rows="3" /></label>
  <label class="field"><span>{{ $t("event.form.triggerTime") }}</span><input v-model="form.triggerTime" type="datetime-local" required /></label>
  <label class="field"><span>{{ $t("event.form.priority") }}</span><select v-model="form.prio"><option value="low">{{ $t("event.priority.low") }}</option><option value="mid">{{ $t("event.priority.mid") }}</option><option value="high">{{ $t("event.priority.high") }}</option></select></label>
  <div class="form-actions field--wide"><button class="button button--primary" type="submit">{{ $t("common.create") }}</button></div>
</form></template>
