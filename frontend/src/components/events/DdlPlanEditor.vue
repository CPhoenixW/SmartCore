<script setup lang="ts">
import type { DdlPlan } from "@/types/event";
import { localInputToIso, toLocalInput } from "@/utils/date";

const plans = defineModel<DdlPlan[]>({ required: true });
function addPlan() {
  plans.value = [...plans.value, { planRole: "manual", stTime: new Date(Date.now() + 3_600_000).toISOString(), durationMin: 30, sortOrder: plans.value.length }];
}
function removePlan(index: number) { plans.value = plans.value.filter((_, itemIndex) => itemIndex !== index); }
function updateTime(index: number, value: string) {
  const plan = plans.value[index];
  if (plan) plan.stTime = localInputToIso(value);
}
</script>
<template>
  <div class="ddl-plans">
    <div v-for="(plan, index) in plans" :key="plan.planEvtId ?? index" class="ddl-plan-row">
      <select v-model="plan.planRole" aria-label="plan role">
        <option value="one_day_before">-1 day</option><option value="one_hour_before">-1 hour</option><option value="manual">manual</option>
      </select>
      <input v-model="plan.title" :placeholder="$t('event.form.title')" />
      <input type="datetime-local" :value="toLocalInput(plan.stTime)" @input="updateTime(index, ($event.target as HTMLInputElement).value)" />
      <input v-model.number="plan.durationMin" type="number" min="1" aria-label="duration" />
      <button class="icon-button danger" type="button" @click="removePlan(index)">×</button>
    </div>
    <button class="button button--ghost" type="button" @click="addPlan">+ {{ $t("event.form.plans") }}</button>
  </div>
</template>
