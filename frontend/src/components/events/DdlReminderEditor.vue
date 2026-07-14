<script setup lang="ts">
import type { DdlReminder } from "@/types/event";
import { localInputToIso, toLocalInput } from "@/utils/date";

const reminders = defineModel<DdlReminder[]>({ required: true });
function replace(index: number, patch: Partial<DdlReminder>) { reminders.value = reminders.value.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item); }
function addReminder() { reminders.value = [...reminders.value, { title: "", triggerTime: new Date(Date.now() + 3_600_000).toISOString(), prio: "high", enabled: true }]; }
function removeReminder(index: number) { reminders.value = reminders.value.filter((_, itemIndex) => itemIndex !== index); }
</script>

<template>
  <div class="ddl-plans">
    <div v-for="(reminder, index) in reminders" :key="reminder.remindEvtId ?? reminder.evtId ?? index" class="ddl-plan-row">
      <label class="check-field compact"><input :checked="reminder.enabled !== false" :aria-label="$t('event.form.enableReminder')" type="checkbox" @change="replace(index, { enabled: ($event.target as HTMLInputElement).checked })" /></label>
      <input :value="reminder.title ?? ''" :placeholder="$t('event.form.reminderContent')" @input="replace(index, { title: ($event.target as HTMLInputElement).value || null })" />
      <input :value="toLocalInput(reminder.triggerTime)" required type="datetime-local" @input="replace(index, { triggerTime: localInputToIso(($event.target as HTMLInputElement).value) })" />
      <select :value="reminder.prio ?? 'high'" :aria-label="$t('event.form.priority')" @change="replace(index, { prio: ($event.target as HTMLSelectElement).value as DdlReminder['prio'] })"><option value="high">{{ $t('event.priority.high') }}</option><option value="mid">{{ $t('event.priority.mid') }}</option><option value="low">{{ $t('event.priority.low') }}</option></select>
      <button class="icon-button danger" type="button" :aria-label="$t('event.form.deleteReminder')" @click="removeReminder(index)">×</button>
    </div>
    <button class="button button--ghost" type="button" @click="addReminder">+ {{ $t('event.form.addLinkedReminder') }}</button>
  </div>
</template>
