<script setup lang="ts">
import type { DdlPlan } from "@/types/event";
import { localInputToIso, toLocalInput } from "@/utils/date";

const plans = defineModel<DdlPlan[]>({ required: true });

function replace(index: number, patch: Partial<DdlPlan>) {
  plans.value = plans.value.map((plan, itemIndex) => itemIndex === index ? { ...plan, ...patch } : plan);
}

function addPlan() {
  plans.value = [
    ...plans.value,
    {
      planRole: "manual",
      stTime: new Date(Date.now() + 3_600_000).toISOString(),
      durationMin: 30,
      enabled: true,
      sortOrder: plans.value.length,
    },
  ];
}

function removePlan(index: number) {
  plans.value = plans.value
    .filter((_, itemIndex) => itemIndex !== index)
    .map((plan, sortOrder) => ({ ...plan, sortOrder }));
}
</script>

<template>
  <div class="ddl-plans">
    <div v-for="(plan, index) in plans" :key="plan.planEvtId ?? plan.evtId ?? index" class="ddl-plan-row">
      <label class="check-field compact"><input :checked="plan.enabled !== false" type="checkbox" @change="replace(index, { enabled: ($event.target as HTMLInputElement).checked })" /></label>
      <select :value="plan.planRole" aria-label="plan role" @change="replace(index, { planRole: ($event.target as HTMLSelectElement).value as DdlPlan['planRole'] })">
        <option value="one_day_before">-1 day</option>
        <option value="one_hour_before">-1 hour</option>
        <option value="manual">manual</option>
      </select>
      <input :value="plan.title ?? ''" :placeholder="$t('event.form.title')" @input="replace(index, { title: ($event.target as HTMLInputElement).value || null })" />
      <input type="datetime-local" :value="toLocalInput(plan.stTime)" required @input="replace(index, { stTime: localInputToIso(($event.target as HTMLInputElement).value) })" />
      <input :value="plan.durationMin" type="number" min="1" aria-label="duration" @input="replace(index, { durationMin: Math.max(1, Number(($event.target as HTMLInputElement).value) || 1) })" />
      <button class="icon-button danger" type="button" @click="removePlan(index)">×</button>
    </div>
    <button class="button button--ghost" type="button" @click="addPlan">+ {{ $t("event.form.plans") }}</button>
  </div>
</template>
